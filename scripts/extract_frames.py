import cv2
import os

def process_all_videos(base_path):
    for subject in os.listdir(base_path):
        subject_path = os.path.join(base_path, subject)

        if not os.path.isdir(subject_path):
            continue

        for file in os.listdir(subject_path):
            if file.endswith(".avi"):
                video_path = os.path.join(subject_path, file)

                video_name = f"{subject}_{file.replace('.avi','')}"
                output_dir = f"temp_frames/{video_name}"
                os.makedirs(output_dir, exist_ok=True)

                cap = cv2.VideoCapture(video_path)
                frame_id = 0

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    frame_name = f"{video_name}_{frame_id}.jpg"
                    cv2.imwrite(f"dataset/images/{frame_name}", frame)

                    frame_id += 1

                cap.release()
                print(f"Processed {video_name}")