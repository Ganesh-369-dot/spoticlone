from flask import Flask, request, jsonify, send_from_directory, make_response
import os
import json
import requests
import glob
import signal
import time
import threading

app = Flask(__name__, static_folder='.')

DOWNLOAD_DIR = "downloads"
DB_FILE = "library.json"

PIPED_APIS = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.syncpundit.io",
    "https://piped-api.garudalinux.org"
]

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- BATTERY SAVER ---
last_active_time = time.time()
@app.before_request
def update_activity():
    global last_active_time
    last_active_time = time.time()

def watchdog():
    while True:
        time.sleep(60)
        if time.time() - last_active_time > 900:
            os.kill(os.getpid(), signal.SIGINT)

threading.Thread(target=watchdog, daemon=True).start()

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f: return json.load(f)
    return {}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f)

ytmusic_client = None
def get_ytmusic():
    global ytmusic_client
    if ytmusic_client is None:
        from ytmusicapi import YTMusic
        ytmusic_client = YTMusic()
    return ytmusic_client

@app.route('/')
def index():
    response = make_response(send_from_directory('.', 'index.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/search', methods=['GET'])
def search():
    try:
        song_query = request.args.get('query')
        if not song_query: return jsonify({"error": "No query provided"}), 400
        
        client = get_ytmusic()
        
        # Pulling 100 songs directly as requested
        search_results = client.search(song_query, filter="songs", limit=100)
        
        formatted_results = []
        for res in search_results:
            thumbnail = res['thumbnails'][-1]['url'] if res.get('thumbnails') else ''
            formatted_results.append({
                "videoId": res['videoId'],
                "title": res['title'],
                "artist": res['artists'][0]['name'] if res.get('artists') else 'Unknown',
                "thumbnail": thumbnail,
                "duration": res.get('duration', '')
            })

        # --- THE "NO MEANS NO" STRICT FILTER ---
        if not formatted_results:
            return jsonify([])

        query_lower = song_query.lower()
        top_artist_lower = formatted_results[0]['artist'].lower()

        is_artist_search = False
        if len(query_lower) > 2 and (query_lower in top_artist_lower):
            is_artist_search = True

        strict_results = []
        for song in formatted_results:
            artist_lower = song['artist'].lower()
            title_lower = song['title'].lower()
            
            if is_artist_search:
                if query_lower in artist_lower:
                    strict_results.append(song)
            else:
                match = False
                for word in query_lower.split():
                    if len(word) > 2 and (word in title_lower or word in artist_lower):
                        match = True
                        break
                if match or len(query_lower) <= 2:
                    strict_results.append(song)

        # UNLOCKED: Returns every single song that passes the filter!
        return jsonify(strict_results)
        
    except Exception as e:
        global ytmusic_client
        ytmusic_client = None
        return jsonify({"error": str(e)}), 500

@app.route('/get_stream', methods=['GET'])
def get_stream():
    video_id = request.args.get('videoId')
    if not video_id: return jsonify({"error": "No video ID provided"}), 400
        
    db = load_db()
    if video_id in db: return jsonify({"stream_url": f"/play_local/{video_id}"})

    best_stream = None
    for api in PIPED_APIS:
        try:
            response = requests.get(f"{api}/streams/{video_id}", timeout=4).json()
            audio_streams = response.get('audioStreams', [])
            if audio_streams:
                for stream in audio_streams:
                    if stream.get('mimeType', '').startswith('audio/mp4') or stream.get('mimeType', '').startswith('audio/m4a'):
                        best_stream = stream['url']
                        break
                if not best_stream: best_stream = audio_streams[0]['url']
                return jsonify({"stream_url": best_stream})
        except: continue 
            
    try:
        import yt_dlp
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {'format': 'bestaudio[ext=m4a]/bestaudio', 'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return jsonify({"stream_url": info['url']})
    except Exception as fallback_error:
        return jsonify({"error": str(fallback_error)}), 500

@app.route('/play_local/<video_id>')
def play_local(video_id):
    valid_exts = ('.m4a', '.mp3', '.webm', '.mp4')
    for file in os.listdir(DOWNLOAD_DIR):
        if file.startswith(video_id) and file.endswith(valid_exts):
            return send_from_directory(DOWNLOAD_DIR, file, conditional=True)
    return jsonify({"error": "File not found"}), 404

@app.route('/image/<video_id>')
def get_image(video_id):
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.jpg")
    if os.path.exists(file_path):
        return send_from_directory(DOWNLOAD_DIR, f"{video_id}.jpg", conditional=True)
    return "", 404

@app.route('/download', methods=['POST'])
def download_song():
    data = request.json
    video_id = data.get('videoId')
    db = load_db()
    if video_id in db: return jsonify({"status": "Already downloaded"})

    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")
    success = False

    try:
        piped_url = None
        for api in PIPED_APIS:
            try:
                res = requests.get(f"{api}/streams/{video_id}", timeout=4).json()
                if res.get('audioStreams'):
                    piped_url = res['audioStreams'][0]['url']
                    break
            except: continue

        if piped_url:
            with requests.get(piped_url, stream=True, timeout=10) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            success = True
    except: pass 

    if not success:
        try:
            import yt_dlp
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio',
                'outtmpl': os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s"),
                'quiet': True, 'no_warnings': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([youtube_url])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    thumb_url = data.get('thumbnail')
    if thumb_url and thumb_url.startswith('http'):
        try:
            with requests.get(thumb_url, stream=True, timeout=5) as r:
                r.raise_for_status()
                with open(os.path.join(DOWNLOAD_DIR, f"{video_id}.jpg"), 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        except: pass 

    db[video_id] = { "videoId": video_id, "title": data.get('title'), "artist": data.get('artist'), "thumbnail": data.get('thumbnail'), "duration": data.get('duration', '') }
    save_db(db)
    return jsonify({"status": "Download Complete!"})

@app.route('/delete', methods=['POST'])
def delete_songs():
    data = request.json
    video_ids = data.get('videoIds', [])
    db = load_db()
    deleted_count = 0
    for vid in video_ids:
        if vid in db: del db[vid]
        for file_path in glob.glob(os.path.join(DOWNLOAD_DIR, f"{vid}.*")):
            try: os.remove(file_path)
            except: pass
        deleted_count += 1
    save_db(db)
    return jsonify({"status": f"Deleted {deleted_count} tracks"})

@app.route('/library', methods=['GET'])
def get_library():
    db = load_db()
    return jsonify(list(db.values()))

@app.route('/radio', methods=['GET'])
def get_radio():
    try:
        video_id = request.args.get('videoId')
        client = get_ytmusic()
        watch_playlist = client.get_watch_playlist(videoId=video_id, limit=20)
        tracks = watch_playlist.get('tracks', [])
        formatted_results = []
        for track in tracks:
            thumbnail = track['thumbnails'][-1]['url'] if track.get('thumbnails') else ''
            duration = track.get('length', '')
            formatted_results.append({ "videoId": track['videoId'], "title": track['title'], "artist": track['artists'][0]['name'] if track.get('artists') else 'Unknown', "thumbnail": thumbnail, "duration": duration })
        return jsonify(formatted_results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/lyrics', methods=['GET'])
def get_lyrics():
    try:
        title = request.args.get('title')
        artist = request.args.get('artist')
        url = f"https://lrclib.net/api/search?track_name={title}&artist_name={artist}"
        response = requests.get(url, timeout=5).json()
        if response and len(response) > 0:
            synced_lyrics = response[0].get('syncedLyrics')
            if synced_lyrics: return jsonify({"lyrics": synced_lyrics})
        return jsonify({"error": "No synced lyrics found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
