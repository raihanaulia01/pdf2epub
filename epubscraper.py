import requests
from bs4 import BeautifulSoup
from ebooklib import epub
import os
import ColorPrint as colorPrint
from urllib.parse import urlparse

def fetch_content(url):
    print(f"\nFetching URL {url}")
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract title
    post_title_div = soup.find('div', class_="post-title")
    title = "Untitled"
    if post_title_div:
        h2_after_post_title = post_title_div.find_next('h2')
        if h2_after_post_title:
            title = h2_after_post_title.text.strip()
    print(f"set title as {title}")
  
    # Extract post content
    article = soup.select(".post-body")[0]
    if len(article) < 1:
        colorPrint.red("No post body found")
        return title, "", {}
    
    # article = soup.find('article')
    # if not article:
    #     colorPrint.red(f"Warning: No <article> found in {url}")
    #     return title, "", {}

    content = ""
    images = {}
    
    for element in article.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'img', 'hr']):
        colorPrint.darkgrey(f"[DEBUG] Element | {element}")
        if element.name == 'img':
            img_url = element['src']
            img_name = os.path.basename(urlparse(img_url).path)

            try:
                colorPrint.blue(f"Retrieving image {img_url}")
                headers = {
                    "Referer": url,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                img_data = requests.get(img_url, headers=headers).content
                images[img_name] = img_data
                content += f'<img src="images/{img_name}" />'
            except requests.exceptions.RequestException as e:
                colorPrint.red(f"Failed to fetch image {img_url}: {e}")
        else:
            # content += f"<p>{element.text}</p>"
            content += str(element)
        if element.name == 'hr': 
            colorPrint.lightgreen(f"Reached end of article {title}\n")
            break
    
    return title, content, images

def create_epub(chapters, output_filename, title, author):
    colorPrint.cyan("Creating EPUB...")
    book = epub.EpubBook()
    book.set_identifier("")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
    
    epub_chapters = []
    
    for i, (title, content, images) in enumerate(chapters):
        chapter = epub.EpubHtml(title=title, file_name=f'chapter_{i}.xhtml', lang='en')
        chapter.content = f"<h1>{title}</h1>{content}"
        epub_chapters.append(chapter)
        book.add_item(chapter)
        
        # Add images to the book
        for img_name, img_data in images.items():
            img_item = epub.EpubItem(uid=img_name, file_name=f'images/{img_name}', media_type='image/jpeg', content=img_data)
            book.add_item(img_item)
    
    # Define the book spine and TOC
    book.toc = epub_chapters
    book.spine = ['nav'] + epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Write the EPUB file
    epub.write_epub(output_filename, book, {})
    colorPrint.green(f"\nEPUB file '{output_filename}' created successfully.\n")

# List of WordPress links (one per chapter). This is ordered.
linksV1 = [
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-illustrations.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-prologue.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c1.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c2.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c3.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c4.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c5.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c6.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-i1.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c7.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c8.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c9.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c10.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-c11.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-epilogue.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-afterword.html",
    "https://yukikitsuneko.blogspot.com/2025/02/love-ranking-v1-ss1.html",
]

title = input('Enter title: ')
author = input('Enter author: ')

chapters = [fetch_content(url) for url in linksV1]
fileName = title+'_V1.epub'
create_epub(chapters, fileName, title, author)