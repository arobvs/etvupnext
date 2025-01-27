
import os
import random
import time
import requests
import subprocess
import xml.etree.ElementTree as ET
from rapidfuzz import fuzz, process
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
xml_url = os.getenv("XMLTV_URL")
media_files_dir = os.getenv("MEDIA_FILES_DIR")
programmes_dir = os.getenv("PROGRAMMES_DIR")
supported_formats = tuple(os.getenv("SUPPORTED_FORMATS", ".mp4,.mkv,.avi,.mov").split(","))
scan_interval = int(os.getenv("SCAN_INTERVAL", 3600))

def preprocess_filename(filename):
    filename = re.sub(r'(\bS\d{1,2}E\d{1,2}\b)', '', filename)
    filename = re.sub(r'\b(480p|720p|1080p|2160p|HD|UHD|DVDRip|BluRay|BRRip|HDRip)\b', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'[._]', ' ', filename)
    filename = filename.strip()
    return filename

def fetch_program_details(xml_url):
    print(f"[INFO] Fetching XMLTV EPG data from {xml_url}...")
    response = requests.get(xml_url)
    if response.status_code == 200:
        print("[INFO] Successfully fetched EPG data.")
        xml_content = response.content

        tree = ET.ElementTree(ET.fromstring(xml_content))
        root = tree.getroot()

        programs = []
        for programme in root.findall(".//programme"):
            title = programme.find(".//title[@lang='en']").text
            category_elem = programme.find(".//category[@lang='en']")
            category = category_elem.text if category_elem is not None else 'Unknown'
            year_elem = programme.find(".//date")
            year = year_elem.text if year_elem is not None and category.lower() == 'movie' else 'Unknown'
            programs.append({'title': title, 'category': category, 'year': year})

        print(f"[INFO] Extracted {len(programs)} program details.")
        return programs
    else:
        print(f"[ERROR] Failed to fetch EPG data (status code: {response.status_code})")
        return []

def check_if_processed(show_name):
    output_path = os.path.join(programmes_dir, f"{show_name}.mp4")
    if os.path.exists(output_path):
        print(f"[INFO] '{show_name}' has already been processed.")
        return True
    return False

def search_local_filesystem():
    print(f"[INFO] Scanning local filesystem at {media_files_dir} for media files...")
    media_files = []

    for root, dirs, files in os.walk(media_files_dir):
        for file in files:
            if file.endswith(supported_formats) and not file.startswith("._"):
                full_path = os.path.join(root, file)
                media_files.append(full_path)

    print(f"[INFO] Found {len(media_files)} media files in the filesystem.")
    return media_files

def find_best_match(program_title, media_files, year=None):
    print(f"[INFO] Searching for the best match for '{program_title}'...")

    if year and year != 'Unknown':
        program_title = f"{program_title} ({year})"

    processed_media_files = [(preprocess_filename(os.path.basename(file)), file) for file in media_files]

    if not processed_media_files:
        print("[ERROR] No media files found for matching.")
        return None

    try:
        matches = process.extract(program_title, [title for title, path in processed_media_files], scorer=fuzz.partial_ratio)
    except Exception as e:
        print(f"[ERROR] Fuzzy matching failed: {e}")
        return None

    best_match_title, best_score, *_ = matches[0]

    best_match_path = next(path for title, path in processed_media_files if title == best_match_title)
    print(f"[INFO] Best match for '{program_title}': {best_match_path} with score {best_score}")

    return best_match_path if best_score > 60 else None

def extract_clip(show_name, matched_file):
    print(f"[INFO] Extracting a 10-second clip from '{matched_file}' for '{show_name}'...")

    result = subprocess.run(['ffmpeg', '-i', matched_file], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    output = result.stderr.decode('utf-8')
    duration_lines = [line for line in output.split('\n') if 'Duration' in line]

    if not duration_lines:
        print(f"[ERROR] Could not extract duration from '{matched_file}'")
        return

    duration_str = duration_lines[0].split()[1].replace(',', '')
    duration_parts = duration_str.split(':')

    try:
        duration = float(duration_parts[0]) * 3600 + float(duration_parts[1]) * 60 + float(duration_parts[2])
    except ValueError as e:
        print(f"[ERROR] Failed to parse duration: {e}")
        return

    start_time = random.uniform(0, max(0, duration - 10))
    output_path = os.path.join(programmes_dir, f"{show_name}.mp4")

    print(f"[INFO] Extracting 10-second clip starting at {start_time:.2f} seconds...")

    subprocess.run([
        'ffmpeg', '-i', matched_file,
        '-map', '0:v:0',
        '-ss', str(start_time), '-t', '10',
        '-vf', 'scale=1920:1080',
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-crf', '23',
        '-preset', 'medium',
        '-an',
        '-movflags', '+faststart',
        output_path
    ])

    print(f"[INFO] Clip saved as '{output_path}'.")

def process_programs(programs, media_files):
    print(f"[INFO] Processing {len(programs)} programs from the EPG...")
    for program in programs:
        show_name = program['title'].strip()
        year = program['year']

        if check_if_processed(show_name):
            continue

        print(f"[INFO] Processing '{show_name}'...")

        best_match = find_best_match(show_name, media_files, year if program['category'].lower() == 'movie' else None)

        if best_match:
            extract_clip(show_name, best_match)
        else:
            print(f"[WARNING] No suitable file found for '{show_name}'.")

def main():
    if not os.path.exists(programmes_dir):
        os.makedirs(programmes_dir)

    while True:
        print("=======================================================")
        print("Fetching and processing XMLTV EPG...")
        print("=======================================================")

        programs = fetch_program_details(xml_url)
        media_files = search_local_filesystem()
        process_programs(programs, media_files)

        print(f"Processing complete. Waiting for {scan_interval / 3600} hour(s)...")
        time.sleep(scan_interval)

if __name__ == '__main__':
    main()
