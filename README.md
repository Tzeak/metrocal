# Metrograph Movie Calendar

A super simple way to browse Metrograph's movie listings and add them to your calendar. No more copy-pasting showtimes! 🎬

## What's this?

This little app lets you:

- See all upcoming movies at Metrograph
- Check which showings are sold out
- Click through to buy tickets
- Add any movie's showtimes to your calendar with one click

## How to use it locally

1. Run the app:

```bash
pip install -r requirements.txt
python app.py
```

Also I think the routing is kinda messed up because it's hosted on my personal apache server so i manually edited some of the paths lol. Remove the /metrograph in the index.html if it's not working.

2. Open your browser to `http://localhost:5000`

3. Check the movies you want to see

4. Click "Create Calendar" to download an .ics file

5. Open the .ics file to add the movies to your calendar

That's it! Your calendar will now have all the movies you picked, with links to buy tickets. 🎟️
