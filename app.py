from flask import Flask, render_template, jsonify, request, send_file
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from icalendar import Calendar, Event
import os
import json
from dateutil import parser
import requests
import tempfile

app = Flask(__name__)

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
    soup = BeautifulSoup(html_content, 'html.parser')
    movies_data = {}  # Changed to dictionary to group by title
    
    # Find all calendar days
    calendar_days = soup.find_all('div', class_='calendar-list-day')
    print(f"\nFound {len(calendar_days)} calendar days")
    
    for day_idx, day in enumerate(calendar_days, 1):
        print(f"\n--- Processing Day {day_idx} ---")
        
        # Get the date from the date div
        date_div = day.find('div', class_='date')
        if not date_div:
            print("  No date div found, skipping day")
            continue
            
        current_date = date_div.text.strip()
        print(f"  Date found: {current_date}")
        
        # Find all movie items
        movie_items = day.find_all('div', class_='item')
        print(f"  Found {len(movie_items)} movie items for this day")
        
        for item_idx, item in enumerate(movie_items, 1):
            print(f"\n    Processing Movie {item_idx}:")
            showtime_span = item.find('span', class_='calendar-list-showtimes')
            if not showtime_span:
                print("    No showtime span found, skipping movie")
                continue
                
            # Get movie title and time
            title_link = showtime_span.find('a', class_='title')
            time_link = showtime_span.find_all('a')[-1]  # Last link is the time
            
            if not title_link or not time_link:
                print("    Missing title or time link, skipping movie")
                continue
                
            movie_title = title_link.text.strip()
            time_text = time_link.text.strip()
            showtime_url = time_link.get('href', '')
            if showtime_url and not showtime_url.startswith('http'):
                showtime_url = f"https://metrograph.com{showtime_url}"
            
            print(f"    Title: {movie_title}")
            print(f"    Time: {time_text}")
            print(f"    URL: {showtime_url}")
            
            # Check if sold out
            is_sold_out = 'sold_out' in time_link.get('class', [])
            if is_sold_out:
                print("    Movie is sold out")
                
            try:
                # Parse the date and time
                date_time = parser.parse(f"{current_date} {time_text}")
                print(f"    Successfully parsed datetime: {date_time}")
                
                # Create or update movie entry
                if movie_title not in movies_data:
                    movies_data[movie_title] = {
                        'id': movie_title,  # Use title as ID
                        'title': movie_title,
                        'showtimes': []
                    }
                
                # Add showtime to the movie's showtimes list
                movies_data[movie_title]['showtimes'].append({
                    'datetime': date_time.isoformat(),
                    'formatted_time': date_time.strftime('%I:%M %p'),
                    'formatted_date': date_time.strftime('%B %d, %Y'),
                    'sold_out': is_sold_out,
                    'url': showtime_url
                })
                
                print(f"    Added showtime to movie: {movie_title}")
            except Exception as e:
                print(f"    Error parsing datetime: {str(e)}")
                continue
    
    # Convert dictionary to list for API response
    movies_list = list(movies_data.values())
    print(f"\n=== Parsing Complete ===")
    print(f"Total movies found: {len(movies_list)}")
    return movies_list

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/movies')
def get_movies():
    try:
        print("\n=== Loading Movies from Metrograph Website ===")
        html_content = fetch_calendar_data()
        if html_content is None:
            return jsonify({'error': 'Failed to fetch calendar data'}), 500
            
        movies = parse_movie_data(html_content)
        if not movies:
            print("Warning: No movies were parsed from the calendar data")
            return jsonify({'error': 'No movies found'}), 404
        return jsonify(movies)
    except Exception as e:
        print(f"Error processing calendar data: {str(e)}")
        return jsonify({'error': 'Failed to process calendar data'}), 500

@app.route('/api/create-calendar', methods=['POST'])
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

if __name__ == '__main__':
    app.run(debug=True) 