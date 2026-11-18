# it-tools converter backend

Backend riêng cho các tác vụ nặng mà frontend static không làm tốt:

- `POST /convert/office-to-pdf` — docx/doc/pptx/xlsx/odt/md/html/txt → PDF (LibreOffice headless). 1 file trả PDF, nhiều file trả ZIP.
- `POST /convert/pdf-to-text` — PDF → text (pypdf).
- `POST /convert/pdf-to-images` — PDF → ZIP ảnh PNG từng trang (PyMuPDF, `dpi` 72–300).
- `POST /convert/media` — fallback ffmpeg server-side cho file lớn (`format=mp3|wav|ogg|mp4|webm|gif`, `extra_args` tùy chọn).
- `GET /health`

## Chạy local

```bash
cd server
pip install -r requirements.txt
# cần LibreOffice + ffmpeg:
# Ubuntu: sudo apt install libreoffice ffmpeg
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t it-tools-converter ./server
docker run -p 8000:8000 it-tools-converter
```

## Compose (frontend + backend)

Xem `docker-compose.yml` ở root. Frontend đọc `VITE_CONVERTER_API_URL` (mặc định `http://localhost:8000`).
