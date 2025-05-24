from flask import Flask, render_template, jsonify, request, send_file
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar, Event
import os
import json
from dateutil import parser
import requests
import tempfile
import pytz
import re
from dotenv import load_dotenv
import time
import hashlib
from pathlib import Path
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

app = Flask(__name__)

# Set up base directory and cache paths
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
IMAGES_CACHE_DIR = CACHE_DIR / "images"
MOVIES_CACHE_FILE = CACHE_DIR / "movies_cache.json"
CACHE_DURATION = 300  # 5 minutes in seconds

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

def ensure_cache_dirs():
    """Ensure cache directories exist."""
    CACHE_DIR.mkdir(exist_ok=True)
    IMAGES_CACHE_DIR.mkdir(exist_ok=True)

def get_cache_age(file_path):
    """Get the age of a cache file in seconds."""
    if not file_path.exists():
        return float('inf')
    return time.time() - file_path.stat().st_mtime

def is_cache_valid(file_path):
    """Check if a cache file is still valid."""
    return get_cache_age(file_path) < CACHE_DURATION

def get_cached_movies():
    """Get movies from cache if valid, otherwise return None."""
    if is_cache_valid(MOVIES_CACHE_FILE):
        try:
            with open(MOVIES_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading movies cache: {str(e)}")
    return None

def save_movies_to_cache(movies):
    """Save movies to cache."""
    try:
        with open(MOVIES_CACHE_FILE, 'w') as f:
            json.dump(movies, f)
    except Exception as e:
        print(f"Error saving movies cache: {str(e)}")

def get_image_cache_path(image_path):
    """Get the local cache path for an image."""
    if not image_path:
        return None
    # Create a hash of the image path to use as filename
    image_hash = hashlib.md5(image_path.encode()).hexdigest()
    return IMAGES_CACHE_DIR / f"{image_hash}.jpg"

def get_cached_image(image_path):
    """Get image from cache if exists, otherwise return None."""
    if not image_path:
        return None
    cache_path = get_image_cache_path(image_path)
    if cache_path and cache_path.exists():
        return str(cache_path)
    return None

def save_image_to_cache(image_path, image_data):
    """Save image data to cache."""
    if not image_path or not image_data:
        return
    cache_path = get_image_cache_path(image_path)
    if cache_path:
        try:
            with open(cache_path, 'wb') as f:
                f.write(image_data)
        except Exception as e:
            print(f"Error saving image cache: {str(e)}")

async def search_tmdb_movie_async(session, title):
    """Search for a movie on TMDB asynchronously."""
    try:
        # Clean the title for better matching
        clean_title = re.sub(r'\([^)]*\)', '', title).strip()
        
        # Search TMDB
        async with session.get(
            f"https://api.themoviedb.org/3/search/movie",
            params={
                "api_key": TMDB_API_KEY,
                "query": clean_title,
                "language": "en-US",
                "page": 1
            }
        ) as response:
            response.raise_for_status()
            data = await response.json()
            
            if data["results"]:
                # Get the first result
                movie = data["results"][0]
                poster_path = movie.get("poster_path")
                
                # Cache the poster image if we have a path
                if poster_path:
                    # Remove leading slash if present
                    poster_path = poster_path.lstrip('/')
                    image_url = f"{TMDB_IMAGE_BASE_URL}/{poster_path}"
                    if not get_cached_image(poster_path):
                        try:
                            async with session.get(image_url) as image_response:
                                if image_response.status == 200:
                                    image_data = await image_response.read()
                                    save_image_to_cache(poster_path, image_data)
                                else:
                                    print(f"Failed to fetch image for {title}: {image_response.status}")
                        except Exception as e:
                            print(f"Error caching image for {title}: {str(e)}")
                
                return {
                    "poster_path": poster_path,
                    "backdrop_path": movie.get("backdrop_path"),
                    "overview": movie.get("overview")
                }
    except Exception as e:
        print(f"Error searching TMDB for {title}: {str(e)}")
    return None

async def fetch_movie_data_async(movies):
    """Fetch TMDB data for all movies asynchronously."""
    async with aiohttp.ClientSession() as session:
        tasks = []
        for movie in movies:
            task = search_tmdb_movie_async(session, movie['title'])
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # Update movies with TMDB data
        for movie, tmdb_data in zip(movies, results):
            if tmdb_data:
                movie.update({
                    'poster_path': tmdb_data['poster_path'],
                    'backdrop_path': tmdb_data['backdrop_path'],
                    'overview': tmdb_data['overview']
                })

def fetch_calendar_data():
    print("\n=== Fetching Calendar Data from Metrograph ===")
    url = "https://metrograph.com/calendar/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print("Successfully fetched calendar data")
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching calendar data: {str(e)}")
        return None

def parse_movie_data(html_content):
    print("\n=== Starting Movie Data Parsing ===")
    start_time = time.time()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    movies = []
    movie_titles = set()  # To track unique movies
    
    # Find all calendar days
    calendar_days = soup.find_all('div', class_='calendar-list-day')
    print(f"\nFound {len(calendar_days)} calendar days")
    
    # First pass: collect all unique movies
    for day in calendar_days:
        date_div = day.find('div', class_='date')
        if not date_div:
            continue
            
        current_date = date_div.text.strip()
        print(f"Processing date: {current_date}")
        
        movie_items = day.find_all('div', class_='item')
        for item in movie_items:
            showtime_span = item.find('span', class_='calendar-list-showtimes')
            if not showtime_span:
                continue
                
            title_link = showtime_span.find('a', class_='title')
            if not title_link:
                continue
                
            movie_title = title_link.text.strip()
            if movie_title not in movie_titles:
                movie_titles.add(movie_title)
                movies.append({
                    'id': len(movies),
                    'title': movie_title,
                    'showtimes': []
                })
    
    print(f"\nFound {len(movies)} unique movies")
    
    # Second pass: collect all showtimes
    for day in calendar_days:
        date_div = day.find('div', class_='date')
        if not date_div:
            continue
            
        current_date = date_div.text.strip()
        movie_items = day.find_all('div', class_='item')
        
        for item in movie_items:
            showtime_span = item.find('span', class_='calendar-list-showtimes')
            if not showtime_span:
                continue
                
            title_link = showtime_span.find('a', class_='title')
            time_link = showtime_span.find_all('a')[-1]
            
            if not title_link or not time_link:
                continue
                
            movie_title = title_link.text.strip()
            time_text = time_link.text.strip()
            showtime_url = time_link.get('href', '')
            if showtime_url and not showtime_url.startswith('http'):
                showtime_url = f"https://metrograph.com{showtime_url}"
            
            is_sold_out = 'sold_out' in time_link.get('class', [])
            
            try:
                date_time = parser.parse(f"{current_date} {time_text}")
                
                # Find the movie in our list and add the showtime
                for movie in movies:
                    if movie['title'] == movie_title:
                        movie['showtimes'].append({
                            'datetime': date_time.isoformat(),
                            'formatted_time': date_time.strftime('%I:%M %p'),
                            'formatted_date': date_time.strftime('%B %d'),
                            'sold_out': is_sold_out,
                            'url': showtime_url
                        })
                        break
                        
            except Exception as e:
                print(f"Error parsing datetime: {str(e)}")
                continue
    
    # Fetch TMDB data asynchronously
    print("\nFetching TMDB data for movies...")
    asyncio.run(fetch_movie_data_async(movies))
    
    end_time = time.time()
    print(f"\n=== Parsing Complete ===")
    print(f"Total movies found: {len(movies)}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    
    return movies

def create_ical_events(selected_movies):
    cal = Calendar()
    
    for movie in selected_movies:
        # Create an event for each showtime of the selected movie
        for showtime in movie['showtimes']:
            event = Event()
            event.add('summary', movie['title'])
            event.add('dtstart', parser.parse(showtime['datetime']))
            event.add('dtend', parser.parse(showtime['datetime']) + timedelta(hours=2))
            event.add('location', 'Metrograph Theater')
            if showtime['url']:
                event.add('url', showtime['url'])
            cal.add_component(event)
    
    # Create a temporary file
    temp_dir = tempfile.gettempdir()
    filename = f"metrograph_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ics"
    filepath = os.path.join(temp_dir, filename)
    
    # Save to temporary file
    with open(filepath, 'wb') as f:
        f.write(cal.to_ical())
    
    return filepath, filename

@app.route('/metrocal/')
def index():
    return render_template('index.html')

@app.route('/metrocal/api/movies')
def get_movies():
    try:
        print("\n=== Loading Movies ===")
        
        # Check cache first
        cached_movies = get_cached_movies()
        if cached_movies:
            print("Returning movies from cache")
            return jsonify(cached_movies)
            
        print("Cache miss, fetching from Metrograph")
        html_content = fetch_calendar_data()
        if html_content is None:
            return jsonify({'error': 'Failed to fetch calendar data'}), 500
            
        movies = parse_movie_data(html_content)
        if not movies:
            print("Warning: No movies were parsed from the calendar data")
            return jsonify({'error': 'No movies found'}), 404
            
        # Save to cache
        save_movies_to_cache(movies)
        
        return jsonify(movies)
    except Exception as e:
        print(f"Error processing calendar data: {str(e)}")
        return jsonify({'error': 'Failed to process calendar data'}), 500

@app.route('/metrocal/api/create-calendar', methods=['POST'])
def create_calendar():
    try:
        data = request.get_json()
        selected_movies = data.get('selectedMovies', [])
        
        if not selected_movies:
            return jsonify({'error': 'No movies selected'}), 400
            
        filepath, filename = create_ical_events(selected_movies)
        
        # Send the file for download
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='text/calendar'
        )
    except Exception as e:
        print(f"Error creating calendar: {str(e)}")
        return jsonify({'error': 'Failed to create calendar'}), 500

@app.route('/metrocal/api/image/<path:image_path>')
def get_image(image_path):
    """Serve images from cache or fetch from TMDB."""
    try:
        # Remove leading slash if present
        image_path = image_path.lstrip('/')
        
        # Check cache first
        cached_image = get_cached_image(image_path)
        if cached_image:
            return send_file(cached_image, mimetype='image/jpeg')
            
        # If not in cache, fetch from TMDB
        image_url = f"{TMDB_IMAGE_BASE_URL}/{image_path}"
        response = requests.get(image_url)
        
        if response.status_code == 200:
            # Save to cache
            save_image_to_cache(image_path, response.content)
            return send_file(
                get_image_cache_path(image_path),
                mimetype='image/jpeg'
            )
        else:
            print(f"Failed to fetch image from TMDB: {response.status_code}")
            return jsonify({'error': 'Image not found'}), 404
            
    except Exception as e:
        print(f"Error serving image: {str(e)}")
        return jsonify({'error': 'Failed to serve image'}), 500

# Initialize cache directories when app starts
ensure_cache_dirs()

if __name__ == '__main__':
    app.run(debug=True) 