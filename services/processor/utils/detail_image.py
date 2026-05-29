from bs4 import BeautifulSoup
import re

def extract_images_from_detail_content(image_detail: str | None) -> list[str]:
    if not image_detail or not str(image_detail).strip():
        return []
    
    content = str(image_detail).strip()
    
    # If it's just a raw URL
    if re.match(r'^https?://[^\s<>"]+$', content):
        return [content]
    
    # If it contains HTML
    try:
        soup = BeautifulSoup(content, 'html.parser')
        images = []
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                images.append(src)
        return images
    except Exception:
        return []
