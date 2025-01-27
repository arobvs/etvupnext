import os
import random
import requests
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import subprocess
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
xml_url = os.getenv("XMLTV_URL")
font_path = os.getenv("FONT_PATH", "./melt.otf")
output_image = os.getenv("OUTPUT_IMAGE", "./output/overlay.png")
output_video = os.getenv("OUTPUT_VIDEO", "./output/final_output.mp4")
template_dir = os.getenv("TEMPLATE_DIR", "./templates/")
programmes_dir = os.getenv("PROGRAMMES_DIR", "./programmes/")

def fetch_xml(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    return None

def parse_epg_time(time_str):
    time_format = "%Y%m%d%H%M%S %z"
    return datetime.strptime(time_str, time_format)

def calculate_show_timings(programmes):
    now = datetime.now()

    for idx, programme in enumerate(programmes):
        if idx == 0:
            programme['time_text'] = "Now"
        elif idx == 1:
            first_show_duration = programmes[0]['duration']
            programme['time_text'] = f"In {int(first_show_duration)} Minutes"
        elif idx == 2:
            first_show_duration = programmes[0]['duration']
            second_show_duration = programmes[1]['duration']
            total_duration = first_show_duration + second_show_duration
            programme['time_text'] = f"In {int(total_duration)} Minutes"

    return programmes

def get_next_programmes(xml_data):
    root = ET.fromstring(xml_data)
    programmes = []
    now = datetime.now(datetime.now().astimezone().tzinfo)

    for programme in root.findall('programme'):
        start_time = parse_epg_time(programme.attrib['start'])
        stop_time = parse_epg_time(programme.attrib['stop'])

        if start_time > now:
            title = programme.find('title').text
            duration_of_show = (stop_time - start_time).total_seconds() // 60

            programmes.append({
                'title': title,
                'start': start_time,
                'stop': stop_time,
                'duration': duration_of_show
            })

        if len(programmes) == 3:
            break

    return programmes

def wrap_text(text, font, max_width):
    lines = []
    words = text.split()
    current_line = ''
    for word in words:
        test_line = current_line + ' ' + word if current_line else word
        bbox = font.getbbox(test_line)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def draw_text_with_border(draw, text, position, font, text_color, border_color, border_width):
    x, y = position
    for dx in range(-border_width, border_width + 1):
        for dy in range(-border_width, border_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=border_color)
    draw.text(position, text, font=font, fill=text_color)

def create_overlay_image(programmes, output_path, font_path):
    img = Image.new('RGBA', (1920, 1080), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    font_upnext = ImageFont.truetype(font_path, 100)
    font_title = ImageFont.truetype(font_path, 40)
    font_time = ImageFont.truetype(font_path, 40)

    yellow = (255, 228, 0, 255)
    black = (0, 0, 0, 255)

    draw_text_with_border(draw, "Up Next", (190, 130), font_upnext, yellow, black, 5)

    x_positions = [190, 730, 1270]
    max_text_width = 460

    for idx, programme in enumerate(programmes):
        time_text = programme['time_text']
        draw_text_with_border(draw, time_text, (x_positions[idx], 630), font_time, yellow, black, 5)

    for idx, programme in enumerate(programmes):
        title = programme['title']
        lines = wrap_text(title, font_title, max_text_width)
        line_height = font_title.getbbox('A')[3] - font_title.getbbox('A')[1] + 5
        total_text_height = len(lines) * line_height
        y_start = 720 - (total_text_height - line_height) / 2

        for i, line in enumerate(lines):
            position = (x_positions[idx], y_start + i * line_height)
            draw_text_with_border(draw, line, position, font_title, yellow, black, 5)

    img.save(output_path, "PNG")

def overlay_ffmpeg(bg_video, overlay_image, output_video, programme_files):
    filter_complex = "[0:v][1:v]overlay=0:0[bg]"
    positions = [(190, 325), (730, 325), (1270, 325)]

    for i, (x, y) in enumerate(positions):
        filter_complex += f";[{i+2}:v]scale=460:258[thumb{i}];[bg][thumb{i}]overlay={x}:{y}[bg]"

    filter_complex += ";[bg]null[outv]"

    ffmpeg_cmd = [
        "ffmpeg",
        "-i", bg_video,
        "-i", overlay_image,
    ]

    for prog_file in programme_files:
        if prog_file is not None:
            ffmpeg_cmd.extend(["-i", prog_file])
        else:
            print(f"[ERROR] Programme file {prog_file} is None. Exiting.")
            return

    ffmpeg_cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-t", "10",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "veryfast",
        "-y", output_video
    ])

    subprocess.run(ffmpeg_cmd)

def get_random_template_video(template_dir):
    return os.path.join(template_dir, random.choice(os.listdir(template_dir)))

def main_loop():
    while True:
        xml_data = fetch_xml(xml_url)
        if xml_data:
            programmes = get_next_programmes(xml_data)
            programmes = calculate_show_timings(programmes)

            print("Generating the overlay image...")
            create_overlay_image(programmes, output_image, font_path)

            random_bg_video = get_random_template_video(template_dir)
            print(f"Using background video: {random_bg_video}")

            programme_files = []
            for programme in programmes:
                programme_file = os.path.join(programmes_dir, f"{programme['title']}.mp4")
                if os.path.exists(programme_file):
                    programme_files.append(programme_file)
                else:
                    programme_files.append(None)

            overlay_ffmpeg(random_bg_video, output_image, output_video, programme_files)

            print(f"Video saved as {output_video}")

        if programmes:
            next_start_time = programmes[0]['start']
            now = datetime.now(next_start_time.tzinfo)
            delay = (next_start_time - now).total_seconds() + 60
            print(f"Next process will run in {int(delay)} seconds.")
            time.sleep(max(delay, 0))

if __name__ == "__main__":
    main_loop()