from flask import Flask, request, jsonify, render_template, send_from_directory
from yt_dlp import YoutubeDL
import os
import tempfile
import traceback
import subprocess
import logging
from pathlib import Path
import shutil
import zipfile
from datetime import datetime

# Caminhos adaptados para ambiente Render (diretório local)
BASE_DIR = Path(__file__).parent.resolve()
TEMPLATES_PATH = BASE_DIR / "templates"
DOWNLOADS_DIR = BASE_DIR / "downloads"
TIKTOK_COOKIE_PATH = BASE_DIR / "cookies" / "tiktok_cookies.txt"  # Ajuste se quiser usar cookies

app = Flask(__name__, template_folder=str(TEMPLATES_PATH))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['UPLOAD_FOLDER'] = 'uploads'

Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YDL_OPTIONS = {
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
    'restrictfilenames': True,
    'noplaylist': True,
}

def load_tiktok_cookies_from_file():
    if not TIKTOK_COOKIE_PATH.exists():
        logger.warning(f"Arquivo de cookies não encontrado em: {TIKTOK_COOKIE_PATH}")
        return None
    logger.info("Cookies do TikTok carregados com sucesso (cookies.txt)")
    return str(TIKTOK_COOKIE_PATH)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/spotify")
def spotify_interface():
    return render_template("spotify.html")

@app.route("/baixar", methods=["POST"])
def baixar():
    try:
        data = request.get_json()
        url = data.get("url")
        platform = data.get("plataforma", "").lower()
        media_type = data.get("tipo", "").lower()

        if not url:
            return jsonify({"status": "error", "message": "URL não fornecida"}), 400

        ydl_opts = {
            **YDL_OPTIONS,
            'format': 'bestaudio[ext=m4a]/bestaudio/best' if media_type == "audio" else 'bestvideo+bestaudio/best',
            'outtmpl': str(DOWNLOADS_DIR / '%(title)s.%(ext)s'),
        }

        if platform == "tiktok":
            cookie_path = load_tiktok_cookies_from_file()
            if cookie_path:
                ydl_opts['cookiefile'] = cookie_path

        if media_type == "audio":
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return jsonify({"status": "error", "message": "Não foi possível extrair informações"}), 400

            filename = ydl.prepare_filename(info)
            if media_type == "audio":
                filename = os.path.splitext(filename)[0] + '.mp3'

            if not os.path.exists(filename):
                return jsonify({"status": "error", "message": "Arquivo baixado não encontrado"}), 500

            return jsonify({
                "status": "success",
                "message": "Download concluído",
                "filename": os.path.basename(filename),
                "local_url": f"/download_temp/{os.path.basename(filename)}",
            })

    except Exception as e:
        logger.error(f"ERRO: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "status": "error",
            "message": f"Falha no download: {str(e)}",
            "error_type": type(e).__name__
        }), 500

@app.route('/listar_spotify', methods=['POST'])
def listar_spotify():
    try:
        data = request.get_json()
        url = data.get("url")

        if not url:
            return jsonify({"status": "error", "message": "URL da playlist não fornecida"}), 400

        cmd = ["spotdl", "list", url]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return jsonify({
                "status": "error",
                "message": "Erro ao listar músicas da playlist",
                "details": result.stderr
            }), 500

        lines = result.stdout.strip().splitlines()
        musicas = [line.strip() for line in lines if line.strip()]

        if not musicas:
            return jsonify({"status": "error", "message": "Nenhuma música encontrada na playlist"}), 404

        return jsonify({
            "status": "success",
            "musicas": musicas[:100]
        })

    except Exception as e:
        logger.error(f"Erro ao listar músicas do Spotify: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "status": "error",
            "message": f"Falha ao listar músicas: {str(e)}"
        }), 500

@app.route('/baixar_spotify', methods=['POST'])
def baixar_spotify():
    try:
        data = request.get_json()
        url = data.get("url")
        selecionadas = data.get("musicas", [])

        if not url:
            return jsonify({"status": "error", "message": "URL não fornecida"}), 400

        temp_dir = tempfile.mkdtemp(dir=str(DOWNLOADS_DIR))
        logger.info(f"Diretório temporário criado: {temp_dir}")

        if not selecionadas:
            cmd = ["spotdl", "download", url, "--output", temp_dir]
        else:
            list_file = Path(temp_dir) / "selected.txt"
            with open(list_file, 'w') as f:
                for music in selecionadas:
                    f.write(music + '\n')
            cmd = ["spotdl", "download", "--output", temp_dir, "--search-file", str(list_file)]

        logger.info(f"Executando comando: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.error(f"Erro no spotdl: {result.stderr}")
            return jsonify({
                "status": "error",
                "message": "Erro ao baixar músicas selecionadas do Spotify",
                "details": result.stderr
            }), 500

        downloaded_files = list(Path(temp_dir).glob("*.*"))
        if not downloaded_files:
            return jsonify({
                "status": "error",
                "message": "Nenhuma música foi baixada"
            }), 404

        if len(downloaded_files) > 1:
            zip_filename = f"spotify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_path = DOWNLOADS_DIR / zip_filename

            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file in downloaded_files:
                    zipf.write(file, arcname=file.name)

            shutil.rmtree(temp_dir)

            return jsonify({
                "status": "success",
                "message": "Músicas baixadas com sucesso",
                "filename": zip_filename,
                "local_url": f"/download_temp/{zip_filename}",
                "is_zip": True
            })

        else:
            file_path = downloaded_files[0]
            final_path = DOWNLOADS_DIR / file_path.name
            file_path.rename(final_path)
            shutil.rmtree(temp_dir)

            return jsonify({
                "status": "success",
                "message": "Música baixada com sucesso",
                "filename": final_path.name,
                "local_url": f"/download_temp/{final_path.name}",
                "is_zip": False
            })

    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "error",
            "message": "Tempo limite excedido ao baixar do Spotify"
        }), 500

    except Exception as e:
        logger.error(f"Erro ao baixar músicas do Spotify: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "status": "error",
            "message": f"Erro ao baixar músicas do Spotify: {str(e)}"
        }), 500

@app.route("/download_temp/<filename>")
def download_temp(filename):
    try:
        file_path = DOWNLOADS_DIR / filename

        if file_path.suffix == ".zip":
            return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True, mimetype='application/zip')

        if not file_path.exists():
            for ext in ['.mp3', '.m4a', '.mp4', '.webm']:
                alt_path = file_path.with_suffix(ext)
                if alt_path.exists():
                    file_path = alt_path
                    break

        if not file_path.exists():
            return jsonify({"status": "error", "message": "Arquivo não encontrado"}), 404

        mimetype = None
        if file_path.suffix == '.mp3':
            mimetype = 'audio/mpeg'
        elif file_path.suffix == '.mp4':
            mimetype = 'video/mp4'

        return send_from_directory(DOWNLOADS_DIR, file_path.name, as_attachment=True, mimetype=mimetype)

    except Exception as e:
        logger.error(f"Erro ao servir arquivo: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
