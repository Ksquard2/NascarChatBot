from flask import Flask, jsonify, request, render_template, Response, abort
import json
import requests
import os
import time

app = Flask(__name__)

VIDEO_PATH = "video.mp4"

def parse_range(range_header, file_size):
    # Example: "bytes=0-1023"
    if not range_header or "=" not in range_header:
        return None
    units, rng = range_header.split("=", 1)
    if units != "bytes":
        return None
    start_end = rng.split("-")
    try:
        start = int(start_end[0]) if start_end[0] else 0
        end = int(start_end[1]) if len(start_end) > 1 and start_end[1] else file_size - 1
    except ValueError:
        return None
    if start > end or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end

def download_generation(video_url, headers, dest_path):
    """Download video to temporary file, then atomically rename to avoid partial reads."""
    tmp = dest_path + ".part"
    
    with requests.get(video_url, headers=headers, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
            f.flush()
            os.fsync(f.fileno())  # Ensure all data is written to disk
    
    # Atomic swap so the web server never reads a half-written file
    os.replace(tmp, dest_path)

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/llm', methods=['POST'])
def nascarLLM(promptP):
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    prePrompt = """
    You are a NASCAR expert and teacher. When answering the user’s question, explain it in a way that even someone brand new to the sport can understand.
        * Start with a simple, 1–2 sentence answer.
        * Then give a deeper explanation using easy language, analogies, or step-by-step breakdowns.
        * If the question involves strategy (like pit stops, tire wear, drafting, fuel windows, etc.), suggest how it could be simulated or visualized.
        * Avoid assuming any prior knowledge of racing terms — define them when first used.
        * Keep it conversational, clear, and friendly.
    """
    prompt = prePrompt+promptP
    api_url = f"https://helloworld3028727102.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2025-01-01-preview"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_API_KEY,
    }
    data = {
        "messages": [
            {"role": "system", "content": "You are an AI coding assistant."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=120)
        if response.status_code == 200:
            api_response = response.json()
            content = api_response['choices'][0]['message']['content']
            if not isinstance(content, str):
                content = str(content)
            return jsonify({"result":content}) 
        else:
            return f"Bad call response code {response.status_code}"
    except requests.RequestException as e:
        last_err = RuntimeError(f"Request to Azure OpenAI failed: {e}")
        return jsonify({"error": str(last_err)}) 

@app.route('/generate-video', methods=['GET'])
def generate_video():
    """Generate video and download to disk atomically."""
    AZURE_Video_Key = os.getenv("AZURE_Video_Key")
    prePrompt = """
    Generate a NASCAR simulation video concept based on the explanation above. The video should:
    • Clearly visualize the scenario described in the answer (e.g., pit stop timing, strategy comparison, caution flag effects, tire wear, or fuel levels).
    • Show cars on track from a simple top-down or broadcast-style view.
    • Use labels or commentary to explain what is happening in beginner-friendly language.
    • If strategy is involved, show two scenarios side-by-side or sequentially (e.g., pitting under caution vs. staying out).
    • Include a short narration script or on-screen text to go with each scene.
    • Keep the tone educational and easy to understand for someone new to NASCAR.
    """
    curr = """
    Ferrari cars are shaped in a sleek, aerodynamic design to help them cut through the air more 
    efficiently, allowing for higher speeds on the racetrack. To understand this better, think of 
    a fish swimming through water. A fish has a streamlined body that helps it move smoothly 
    with less effort. If a fish were bulky and flat, it would struggle to swim fast because 
    of all the resistance from the water. Similarly, a Ferrari has a shape that minimizes 
    "drag," which is the force that pushes against the car as it moves through the air. The curvy 
    lines and pointed nose of a Ferrari help direct airflow around the car, which enhances stability and speed. 
    If you want to visualize this concept, imagine blowing air through a piece of paper folded like a 
    plane versus a flat piece of paper. The folded paper glides better, just like the curves of a 
    Ferrari help it glide through the air at high speeds. Additionally, the design isn't just about 
    speed; it also aids in controlling how the car handles turns and tracks on a racetrack.
    """
    prompt = prePrompt+curr
    api_url = "https://ahmed-mhgriz8w-eastus2.openai.azure.com/openai/v1/video/generations/jobs?api-version=preview"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_Video_Key,
    }
    # Step 1: POST to create the job
    job_data = {
        "model": "sora",
        "prompt": prompt,
        "height": 720,
        "width": 1280,
        "n_seconds": 5,
        "n_variants": 1
    }
    try:
        response = requests.post(api_url, headers=headers, json=job_data, timeout=120)
        print('Azure POST response:', response.status_code, response.text)
        if response.status_code != 200 and response.status_code != 201:
            return jsonify({"error": f"Bad call response code {response.status_code}"}), response.status_code
        job_response = response.json()
        job_id = job_response.get("id")
        if not job_id:
            print('No job id in Azure response:', job_response)
            return jsonify({"error": "No job id returned from Azure."}), 500
        # Step 2: Poll for job status
        status_url = f"https://ahmed-mhgriz8w-eastus2.openai.azure.com/openai/v1/video/generations/jobs/{job_id}?api-version=preview"
        poll_headers = headers
        max_wait = 300  # seconds (was 60)
        interval = 10   # seconds (was 5)
        waited = 0
        generation_id = None
        while waited < max_wait:
            status_resp = requests.get(status_url, headers=poll_headers)
            print('Azure status response:', status_resp.status_code, status_resp.text)
            status_json = status_resp.json()
            if status_json.get("status") == "succeeded" and status_json.get("generations"):
                print('Azure succeeded status_json:', status_json)
                gen = status_json["generations"][0]
                print('First generation object:', gen)
                generation_id = gen.get("id")
                break
            elif status_json.get("status") == "failed":
                print('Azure job failed:', status_json)
                return jsonify({"error": "Video generation failed."}), 500
            time.sleep(interval)
            waited += interval
        if not generation_id:
            print('No generation id found after polling.')
            return jsonify({"error": "No generation id found after polling."}), 500
        # Step 3: Download the video to disk atomically
        video_url = f"https://ahmed-mhgriz8w-eastus2.openai.azure.com/openai/v1/video/generations/{generation_id}/content/video?api-version=preview"
        try:
            download_generation(video_url, headers, VIDEO_PATH)
            print(f'Video downloaded successfully to {VIDEO_PATH}')
            return jsonify({"status": "success", "message": "Video generated and ready"}), 200
        except requests.RequestException as e:
            print('Failed to download video:', e)
            return jsonify({"error": f"Failed to download video: {str(e)}"}), 500
    except requests.RequestException as e:
        last_err = RuntimeError(f"Request to Azure OpenAI failed: {e}")
        print('RequestException:', last_err)
        return jsonify({"error": str(last_err)}), 400

@app.route("/video", methods=["GET"])
def serve_video():
    """Serve video file with proper Range request support (206 Partial Content)."""
    if not os.path.exists(VIDEO_PATH):
        abort(404)

    file_size = os.path.getsize(VIDEO_PATH)
    range_header = request.headers.get("Range", None)
    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
    }

    if range_header:
        rng = parse_range(range_header, file_size)
        if rng is None:
            # Range not satisfiable
            return Response(status=416, headers={
                **headers, "Content-Range": f"bytes */{file_size}"
            })
        start, end = rng
        length = end - start + 1

        with open(VIDEO_PATH, "rb") as f:
            f.seek(start)
            data = f.read(length)

        return Response(
            data, 206,
            headers={
                **headers,
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
            },
        )

    # Full file
    with open(VIDEO_PATH, "rb") as f:
        data = f.read()
    headers["Content-Length"] = str(file_size)
    return Response(data, 200, headers=headers)

if __name__ == '__main__':
    app.run(debug=True)
