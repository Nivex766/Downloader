# Use imagem base com Python
FROM python:3.11-slim

# Instala dependências do sistema e o ffmpeg
RUN apt-get update && apt-get install -y ffmpeg gcc

# Cria diretório da aplicação
WORKDIR /app

# Copia os arquivos
COPY . /app

# Instala dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta usada pelo Flask
EXPOSE 8080

# Comando para rodar o servidor
CMD ["python", "app.py"]
