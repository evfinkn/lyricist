# lyricist

Genius allows you to search for songs containing a specific lyric. However, it doesn't allow you to search
only a specific artist's songs for a specific lyric. This script allows you to do exactly that.

## Setup

This script requires [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) and
[Requests](https://requests.readthedocs.io/en/latest/). To install them, run
```
pip3 install beautifulsoup4 requests
```
You'll also need an account with access to the [Genius API](https://genius.com/signup_or_login).
These accounts are free. Once you have an account, you'll need to get your access token to use
the script.

## Usage

Run the script using
```
python3 lyricist.py -t "TOKEN" "ARTIST" "LYRIC"
```

If `-t "TOKEN"` is not specified, it is assumed to be in the `GENIUS_ACCESS_TOKEN` environemtn variable.  
To see the list of all options, run
```
python3 lyricist.py -h
```

## Notes

Since fetching an artist's songs' lyrics is time-consuming, the script will create a directory titled "artists"
in the same directory the script is in and save every fetched artist in that directory. Any future searches
will then use the cached lyrics to save time.
