import urllib.request
import os
import time
import zipfile

URL = "https://github.com/leapbtw/uxplay-windows/releases/download/2.0.0.1736/uxplay-windows.zip"
TARGET_FILE = os.path.join("engine", "bin", "uxplay.zip")
TARGET_DIR = os.path.join("engine", "bin")

os.makedirs(TARGET_DIR, exist_ok=True)

def download_with_resume(url, filename, max_retries=20):
    for attempt in range(max_retries):
        try:
            downloaded = 0
            if os.path.exists(filename):
                downloaded = os.path.getsize(filename)
                
            req = urllib.request.Request(url)
            if downloaded > 0:
                req.headers['Range'] = f'bytes={downloaded}-'
                
            print(f"[Attempt {attempt+1}] Downloading from byte {downloaded}...")
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = downloaded + int(response.headers.get('Content-Length', 0))
                mode = 'ab' if downloaded > 0 else 'wb'
                with open(filename, mode) as f:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\rProgress: {downloaded}/{total_size} bytes ({percent:.1f}%)", end="", flush=True)

            print(f"\nDownload finished ({downloaded} bytes).")
            # Verify zip
            print("Verifying zip file...")
            with zipfile.ZipFile(filename, 'r') as z:
                z.testzip()
                print("Zip file is valid! Extracting...")
                z.extractall(TARGET_DIR)
                print("Extracted successfully!")
            os.remove(filename)
            return True
        except Exception as e:
            print(f"\n[Warning] Attempt {attempt+1} encountered: {e}. Retrying in 2 seconds...")
            time.sleep(2)

    return False

if __name__ == "__main__":
    download_with_resume(URL, TARGET_FILE)
