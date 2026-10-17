import os
import shutil
import re
import fitz
import yt_dlp
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Ensure the downloads directory exists
os.makedirs("downloads", exist_ok=True)

# Mount the static directory to serve the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    # Serve the main HTML page
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

def extract_youtube_links(pdf_path):
    doc = fitz.open(pdf_path)
    yt_links = []
    yt_pattern = re.compile(r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]+')

    for page in doc:
        for link in page.get_links():
            if 'uri' in link:
                url = link['uri']
                if ('youtube.com' in url or 'youtu.be' in url) and url not in yt_links:
                    yt_links.append(url)
                    
        text = page.get_text("text")
        for match in yt_pattern.finditer(text):
            url = match.group()
            if url not in yt_links:
                yt_links.append(url)

    return yt_links

def download_mp3(url, output_folder="downloads"):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': f'{output_folder}/%(title)s.%(ext)s', 
        'quiet': True,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # yt-dlp might download a .webm or .m4a before converting to .mp3
            filename = ydl.prepare_filename(info)
            base_name = os.path.splitext(filename)[0]
            mp3_filename = f"{base_name}.mp3"
            
            return {"url": url, "title": info.get('title'), "file_path": mp3_filename, "status": "success"}
    except Exception as e:
        return {"url": url, "status": "failed", "error": str(e)}

@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    temp_pdf_path = f"temp_{file.filename}"
    with open(temp_pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    links = extract_youtube_links(temp_pdf_path)
    
    results = []
    for link in links:
        result = download_mp3(link)
        results.append(result)
        
    os.remove(temp_pdf_path)
    return {"message": f"Successfully processed {len(links)} links.", "ordered_downloads": results}

@app.get("/download/{filename}")
async def serve_file(filename: str):
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='audio/mpeg')
    return {"error": "File not found"}
