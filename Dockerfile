FROM python:3.11-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Cria diretórios
WORKDIR /app
COPY . /app

# Instala dependências Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Instala o spotdl
RUN pip install spotdl

# Porta usada pelo Flask
ENV PORT=8080

# Comando padrão
CMD ["python", "spot.py"]
