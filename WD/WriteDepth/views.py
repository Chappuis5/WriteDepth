from django.shortcuts import render, redirect
from django.http import HttpResponse
import os
import atexit
import exiftool
from django.http import JsonResponse
import sqlite3
from datetime import datetime, timedelta
import pytz
import json
import subprocess
from zipfile import ZipFile


# Emplacement du répertoire temporaire
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_DIR = os.path.join(BASE_DIR, 'temp_folder')

# Crée le répertoire s'il n'existe pas
if not os.path.exists(TEMP_DIR):
    os.mkdir(TEMP_DIR)

# Fonction à exécuter à la sortie
def cleanup():
    for filename in os.listdir(TEMP_DIR):
        os.remove(os.path.join(TEMP_DIR, filename))
    os.rmdir(TEMP_DIR)

# Enregistre la fonction de nettoyage pour qu'elle soit exécutée lorsque le programme se termine
atexit.register(cleanup)

def index(request):
    return render(request, 'index.html')

def upload(request):
    if request.method == 'POST':
        try:
            uploaded_files = request.FILES.getlist('upload_files')
            for uploaded_file in uploaded_files:
                if uploaded_file.name.lower().endswith('.nef'):
                    with open(os.path.join(TEMP_DIR, uploaded_file.name), 'wb+') as destination:
                        for chunk in uploaded_file.chunks():
                            destination.write(chunk)
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request'})

def upload_db(request):
    if request.method == 'POST':
        try:
            uploaded_file = request.FILES['database_file']
            if uploaded_file.name.lower().endswith('.db'):
                with open(os.path.join(TEMP_DIR, uploaded_file.name), 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
                return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Function to convert Unix timestamp to datetime object with timezone
def unix_to_datetime_with_timezone(unix_timestamp, timezone='UTC'):
    utc_time = datetime.utcfromtimestamp(unix_timestamp).replace(tzinfo=pytz.UTC)
    local_time = utc_time.astimezone(pytz.timezone(timezone))
    return local_time


# Modified function to find matching timestamp and time elapsed
def find_matching_timestamp_with_timezone(date_string, time_string, db_path='dive_book_1.db', timezone='UTC'):
    # Initialize SQLite connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Convert given date and time to datetime objects
    given_date_obj = datetime.strptime(date_string, "%Y:%m:%d")
    given_time_obj = datetime.strptime(time_string, "%H:%M:%S")
    given_datetime = datetime.combine(given_date_obj.date(), given_time_obj.time()).replace(
        tzinfo=pytz.timezone(timezone))

    # Fetch all rows from 'dive_info' table
    cursor.execute("SELECT * FROM dive_info")
    all_rows = cursor.fetchall()

    # List to store IDs and timestamps matching the date
    matching_timestamps = []

    # Loop through records and add matching IDs and timestamps to the list
    for row in all_rows:
        timestamp = row[3]
        timestamp_datetime = unix_to_datetime_with_timezone(timestamp, timezone)
        if timestamp_datetime.date() == given_date_obj.date():
            matching_timestamps.append((row[0], timestamp))

    # Close the SQLite connection
    conn.close()

    # Handling cases with 1 or more matching timestamps
    if len(matching_timestamps) == 1:
        id_value, timestamp_value = matching_timestamps[0]
        matching_timestamp = unix_to_datetime_with_timezone(timestamp_value, timezone)

        # Compare the given time with the timestamp
        if given_datetime < matching_timestamp:
            print(f"{given_datetime} is somehow smaller than matching timestamp")
            time_elapsed = matching_timestamp - given_datetime
        else:
            time_elapsed = given_datetime - matching_timestamp

        return {
            "message": "Only one timestamp",
            "id": id_value,
            "matching_timestamp": matching_timestamp,
            "time_elapsed": time_elapsed
        }

    else:
        for i in range(len(matching_timestamps) - 1):
            current_datetime = unix_to_datetime_with_timezone(matching_timestamps[i][1], timezone)
            next_datetime = unix_to_datetime_with_timezone(matching_timestamps[i + 1][1], timezone)

            if given_datetime >= current_datetime and given_datetime < next_datetime:
                matching_id = matching_timestamps[i][0]
                matching_timestamp = unix_to_datetime_with_timezone(matching_timestamps[i][1], timezone)
                time_elapsed = given_datetime - matching_timestamp

                return {
                    "message": "Multiple timestamps",
                    "id": matching_id,
                    "matching_timestamp": matching_timestamp,
                    "time_elapsed": time_elapsed
                }

    return {"message": "No matching timestamps found"}


def fetch_current_depth_with_confidence(dive_id, time_elapsed, db_path='dive_book_1.db'):
    # Initialize SQLite connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Convert time_elapsed to seconds for comparison
    time_elapsed_seconds = time_elapsed.total_seconds()

    # Fetch records from 'dive_log_records' table based on dive ID
    cursor.execute("SELECT * FROM dive_log_records WHERE diveLogId = ?", (dive_id,))
    records = cursor.fetchall()

    # Close the SQLite connection
    conn.close()

    # Loop through records to find the closest time elapsed
    closest_record = None
    min_time_difference = float('inf')

    for record in records:
        current_time = record[2]
        time_difference = abs(current_time - time_elapsed_seconds)

        if time_difference < min_time_difference:
            min_time_difference = time_difference
            closest_record = record

    if closest_record:
        # Calculate confidence level
        closest_time = closest_record[2]
        if closest_time != 0:
            confidence_level = min(1, time_elapsed_seconds / closest_time)
        else:
            confidence_level = 1  # If closest_time is zero, then it's an exact match, confidence is 100%

        confidence_percentage = confidence_level * 100

        return {
            "message": "Closest record found",
            "dive_id": dive_id,
            "closest_time": closest_time,
            "current_depth": closest_record[3],
            "confidence_percentage": confidence_percentage
        }
    else:
        return {"message": "No records found for this dive ID"}



def process(request):
    if request.method == 'POST':
        image_data = []

        # Locate the .db file in TEMP_DIR
        db_file_path = None
        for filename in os.listdir(TEMP_DIR):
            if filename.lower().endswith('.db'):
                db_file_path = os.path.join(TEMP_DIR, filename)
                break

        if db_file_path is None:
            return HttpResponse("Database file not found.")

        for filename in os.listdir(TEMP_DIR):
            if filename.lower().endswith('.nef'):
                file_path = os.path.join(TEMP_DIR, filename)
                with exiftool.ExifToolHelper() as et:
                    metadata = et.get_metadata([file_path])
                    for d in metadata:
                        datetime_str = d.get("EXIF:DateTimeOriginal", "Unknown")
                        date_string, time_string = datetime_str.split(' ')
                        result1 = find_matching_timestamp_with_timezone(date_string, time_string, db_path=db_file_path,
                                                                        timezone='UTC')

                        if "id" in result1 and "time_elapsed" in result1:
                            dive_id = result1["id"]
                            time_elapsed = result1["time_elapsed"]
                            result2 = fetch_current_depth_with_confidence(dive_id, time_elapsed, db_path=db_file_path)
                            current_depth = result2.get("current_depth", "Unknown")
                            confidence_percentage = result2.get("confidence_percentage", "Unknown")
                        else:
                            current_depth = "Unknown"
                            confidence_percentage = "Unknown"

                        image_data.append({
                            "filename": filename,
                            "datetime": datetime_str,
                            "current_depth": current_depth,
                            "confidence_percentage": confidence_percentage
                        })
        with open(os.path.join(TEMP_DIR, 'metadata.json'), 'w') as f:
            json.dump(image_data, f)

        return render(request, 'your_images.html', {'image_data': image_data})

    return HttpResponse('Processing done.')


def write_meta_data(request):
    if request.method == 'POST':
        try:
            with open(os.path.join(TEMP_DIR, 'metadata.json'), 'r') as f:
                image_data = json.load(f)

            for data in image_data:
                filename = data.get("filename")
                depth = data.get("current_depth", "Unknown")
                confidence = data.get("confidence_percentage", "Unknown")

                comment_str = f"CurrentDepth: {depth}, DepthConfidence: {confidence}"

                file_path = os.path.join(TEMP_DIR, filename)

                # Use exiftool to write metadata
                subprocess.run(["exiftool", "-UserComment=" + comment_str, file_path])

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def download_images(request):
    # Create a ZIP file in memory
    zip_filename = "images.zip"
    zip_file_path = os.path.join(TEMP_DIR, zip_filename)
    with ZipFile(zip_file_path, 'w') as zipf:
        for filename in os.listdir(TEMP_DIR):
            if filename.lower().endswith('.nef'):
                file_path = os.path.join(TEMP_DIR, filename)
                zipf.write(file_path, filename)

    # Read the ZIP file into memory
    with open(zip_file_path, 'rb') as f:
        zip_data = f.read()

    # Remove the ZIP file from disk
    os.remove(zip_file_path)

    # Return as ZIP file download
    response = HttpResponse(zip_data, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename={zip_filename}'
    return response