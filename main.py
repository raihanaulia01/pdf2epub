import pymupdf
from ebooklib import epub
import os
from rich.progress import track
from rich import print as print
from rich.console import Console
from rich.rule import Rule
import click
import re
import inspect
import datetime

HEADER_FOOTER_THRESHOLD = 60
IGNORE_IMAGE_THRESHOLD = 0.7
DEBUG_MODE = False
DO_SAVE_IMG = False

console = Console()

@click.command()
@click.option("--input", "-i", required=True, help="Input PDF file or folder path")
@click.option("--output", "-o", default="output/", help="Output directory (default to output/)")
@click.option("--save-images", is_flag=True, help="Save extracted images from input pdf to disk")
@click.option("--header-threshold", default=60, help="Header/footer threshold for text extraction. default is 60")
@click.option("--img-threshold", default=0.7, help="Image extraction threshold. default is 0.7")
@click.option("--img-prefix", default="", help="Image prefix. Will be used to name the extracted images")
@click.option("--debug", is_flag=True, help="Enable debug mode")

# TODO edge case where the sentence is split into two pages. 
#   e.g. "test \pagebreak\ sentence". this won't combine properly using the current method
#   also when a 'new line' starts with an uppercase letter, but the sentence isn't actually finished yet.
# TODO change image prefix to something more reasonable. Currently doesn't work well with long file names.
def main(input, output, save_images, header_threshold, img_threshold, img_prefix, debug):
    global HEADER_FOOTER_THRESHOLD, IGNORE_IMAGE_THRESHOLD, DEBUG_MODE, DO_SAVE_IMG
    
    HEADER_FOOTER_THRESHOLD = header_threshold
    IGNORE_IMAGE_THRESHOLD = img_threshold
    DEBUG_MODE = debug
    DO_SAVE_IMG = save_images
    
    os.makedirs(output, exist_ok=True)
    filetype_error = True

    if os.path.isfile(input):
        if input.lower().endswith(".pdf"):
            pdf_to_epub(input, output, img_prefix=img_prefix)
            filetype_error = False
    elif os.path.isdir(input):
        pdf_counter = 1
        for filename in os.listdir(input):
            if filename.lower().endswith('.pdf'):
                filetype_error = False
                pdf_path = os.path.join(input, filename)
                pdf_to_epub(pdf_path, output, img_prefix=f"{img_prefix}_{pdf_counter}" if img_prefix else "")
                pdf_counter += 1
    else:
        debug_print("error", f"Error: {input} is not a valid file or directory")
        return
    
    if filetype_error:
        debug_print("error", f"Error: {input} is not or has no PDF.")

def debug_print(level, text, i=None):
    global DEBUG_MODE
    level = level.lower()
    level_color = {
        "info": "white",
        "debug": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold bright_red",
    }

    if i == None:
        print_text = text
    else:
        page = i + 1
        page_debug = f"PAGE {page:3}"
        print_text = f"{page_debug:<9}: {text}"

    context = ""
    if DEBUG_MODE:
        context = inspect.currentframe().f_back.f_code.co_name
        if level in ("success", "warning", "error"):
            context = f"[green]{str(datetime.datetime.now())[:-4]}[/green] | [{level_color[level]}]{level.upper():<9}[/{level_color[level]}] | [bright_blue]{context}[/bright_blue] - "
        else: 
            context = f"[green]{str(datetime.datetime.now())[:-4]}[/green] | [bold white]{level.upper():<9}[/bold white] | [bright_blue]{context}[/bright_blue] - "

    if level in level_color and level not in ("debug", "debug_data"):
        console.print(f"{context}[{level_color[level]}]{print_text}[/{level_color[level]}]")
    if DEBUG_MODE:
        if level == "debug":
            console.print(f"{context}[{level_color[level]}]{print_text}[/{level_color[level]}]")
        elif level == "debug_data":
            console.print(text)


def create_epub(chapters, output_filename, title, author, cover_image=None):
    debug_print("info", f"\nCreating EPUB {output_filename}")
    book = epub.EpubBook()
    book.set_identifier("")
    book.set_title(title)
    debug_print("info", f"Set title to [cyan]\"{title}\"[/cyan]")
    book.set_language("en")
    book.add_author(author)
    debug_print("info", f"Set author to [cyan]\"{author}\"[/cyan]") if author else debug_print("warning", "Author not detected in metadata")

    if cover_image[0] and cover_image[1]:
        debug_print("debug", f"Adding cover image {cover_image[0]}")
        book.set_cover(cover_image[0], cover_image[1])
    
    epub_chapters = []
    
    for i, (chapter_title, content, images) in enumerate(chapters):
        chapter = epub.EpubHtml(title=chapter_title, file_name=f'chapter_{i}.xhtml', lang='en')
        chapter.content = content
        epub_chapters.append(chapter)
        book.add_item(chapter)
        
        # Add images to the book
        for img_name, img_data in images.items():
            img_item = epub.EpubItem(uid=img_name, file_name=f'images/{img_name}', media_type='image/jpeg', content=img_data)
            book.add_item(img_item)

    if not epub_chapters:
        dummy_chapter = epub.EpubHtml(title="Content", file_name='chapter_0.xhtml', lang='en')
        dummy_chapter.content = "<p>No content could be extracted from this PDF.</p>"
        epub_chapters.append(dummy_chapter)

    # Define the book spine and TOC
    book.toc = epub_chapters
    book.spine = ['nav'] + epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Write the EPUB file
    epub.write_epub(output_filename, book)
    debug_print("success", f"EPUB file '{output_filename}' created successfully.\n")

def handle_extract_with_font(span):
    span_font = span["font"].lower()
    if "italic" in span_font and "bold" in span_font:
        return f"<b><i>{span['text']}</i></b>"
    elif "italic" in span_font:
        return f"<i>{span['text']}</i>"
    elif "bold" in span_font:
        return f"<b>{span['text']}</b>"
    else: 
        return span["text"]

def in_header_footer(bbox, page_height):
    return (bbox[1] <= HEADER_FOOTER_THRESHOLD or bbox[1] >= page_height - HEADER_FOOTER_THRESHOLD)

def takes_full_page(bbox, page_rect):
    page_width = page_rect.width
    page_height = page_rect.height
    
    img_width = bbox[2] - bbox[0]
    img_height = bbox[3] - bbox[1]
    
    width_ratio = img_width / page_width
    height_ratio = img_height / page_height
    area_ratio = (img_width * img_height) / (page_width * page_height)

    return area_ratio >= 0.7 or (width_ratio >= 0.8 and height_ratio >= 0.8)

def combine_extract_text_from_lines(lines):
    text = ""
    combined_spans = []
    
    for i, line in enumerate(lines):
        # check if next line starts with lowercase
        should_combine = False
        if i + 1 < len(lines) and lines[i + 1]["spans"]:
            next_first_text = lines[i + 1]["spans"][0]["text"]
            if next_first_text.strip() and next_first_text.strip()[0].islower():
                should_combine = True
        
        if should_combine:
            combined_spans.extend(line["spans"])
            combined_spans.append({"text": " ", "font": ""})  # add space between lines
            continue

        all_spans = combined_spans + line["spans"]
        line_text = ""
        for span in all_spans:
            line_text += handle_extract_with_font(span)
        
        text += f"<p>{line_text}</p>"
        combined_spans = []
    
    return text if text.strip() else "<p> </p>"

def extract_img_from_xref(doc, xref):
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.n - pix.alpha > 3: # CMYK: convert to RGB first
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        return pix
    except Exception as e:
        debug_print("error", f"Failed to extract image xref={xref}:\n{e}")

def sanitize_filename(filename, max_len=40):
    filename = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', filename)
    filename = re.sub(r'\s+', '_', filename.strip())
    if len(filename) > max_len:
        filename = filename[:max_len]
    return filename

def truncate_string(text, max_len):
    if len(text) > max_len:
        return f"{text[:max_len]}..."
    return text

def extract_pdf(doc: pymupdf.Document,start=0, end=None, img_prefix="", show_progress=False):
    end = doc.page_count if end == None else end
    content = ""
    images = {} # key: filename, value: image data
    doc_title = doc.metadata.get("title") if doc.metadata.get("title").strip() != "" else img_prefix
    page_range = range(start, end)
    debug_print("debug", f"extracting pdf {doc_title} from {start} to {end}")

    if show_progress:
        page_range = track(page_range, description=f"[cyan]Processing {doc_title}[/cyan]", console=console)

    for i in page_range:
        page = doc[i]
        page_height = page.rect.height
        dicts = page.get_text("dict", sort=True)
        img_count = 0
        img_list = page.get_images()
        get_images_count = len(img_list)
        ignored_images = set()

        for element in dicts["blocks"]:
            if element["type"] == 0: # text block
                # ignore text blocks in headers and footers
                if in_header_footer(element["bbox"], page_height):
                    continue
                content += combine_extract_text_from_lines(element["lines"])
            
            elif element["type"] == 1: # image
                img_count += 1
                img_data = element["image"]
                img_bbox = element["bbox"]
                img_filename = f"{img_prefix}-page_{i+1}-image_{img_count}.png"

                # ignores images in headers and bottom part of the page (use threshold)
                if not takes_full_page(img_bbox, page.rect) and (
                    (img_bbox[1] > page_height * IGNORE_IMAGE_THRESHOLD) or in_header_footer(img_bbox, page_height)): 
                    debug_print("debug", f"ignored image {img_filename} bbox: {img_bbox}", i=i)
                    ignored_images.add(img_bbox)
                    continue

                # if image is an xref
                if isinstance(img_data, int):
                    xref = img_data
                    if xref == 0:
                        continue
                    
                    pix = extract_img_from_xref(doc, xref)
                    images[img_filename] = pix.tobytes()
                    pix = None
                elif isinstance(img_data, bytes): # otherwise it's the byte data
                    images[img_filename] = img_data
                else:
                    debug_print("error", f"Image not recognized! Img data: \n{img_data}", i=i)
                    continue

                content += f'<img src="images/{img_filename}" alt="Image {img_count} on page {i+1}" />\n'
            else:
                debug_print("error", f"Error: unrecognized block type {element["type"]}", i=i)

        # check if there are any missed images
        if img_count < get_images_count:
            for index, img in enumerate(img_list):
                xref = img[0]
                # debug_print("debug_data", page.get_image_rects(xref))
                try:
                    image_rects = page.get_image_rects(xref)[0] # this returns (x0, y0, x1, y1)
                except IndexError:
                    debug_print("error", f"Image with xref {xref} in page {i+1} doesn't exist")
                    continue
                image_height = image_rects[3] - image_rects[1]
                full_img_filename = f"{img_prefix}-page_{i+1}-full_{index}.png"
                debug_print("debug", f"FULL_IMG | {full_img_filename}")

                if xref == 0:
                    continue
                # image thresholds
                if (image_rects[1] > page_height * IGNORE_IMAGE_THRESHOLD) or (image_height < 5):
                    continue 
                # check duplicates
                if (image_rects in ignored_images):
                    continue

                pix = extract_img_from_xref(doc, img[0])
                full_img_bytes = pix.tobytes()
                
                debug_print("debug", f"Adding image {full_img_filename}", i=i)
                images[full_img_filename] = full_img_bytes
                content += f'<img src="images/{full_img_filename}" alt="Full Image {index} on page {i+1}" />\n'

    return content, images

def extract_with_toc(doc, img_prefix):
    toc = doc.get_toc()
    chapter_list = []
    img_prefix = sanitize_filename(img_prefix)
    
    doc_title = doc.metadata.get("title") if doc.metadata.get("title").strip() != "" else img_prefix

    if not toc:
        debug_print("warning", "Table of contents not found. This book will not have any TOC.")
        content, images = extract_pdf(doc, img_prefix=img_prefix, show_progress=True)
        return [(img_prefix, content, images)]
       
    if toc[0][2] > 1: # include the first pages that are not in the TOC
        toc.insert(0, (1, "No title", 1))

    valid_toc = [item for item in toc if item[1].strip() != ""]
    valid_toc.sort(key=lambda x: x[2]) # sort toc based on the page
    debug_print("debug_data", valid_toc)
    for i, toc_item in enumerate(track(valid_toc, description=f"[cyan]Processing chapters for {truncate_string(doc_title, 67)}[/cyan]", console=console)):
        toc_lvl, toc_title, toc_page = toc_item
        toc_page -= 1  # toc is 1-based. convert to 0-based
        
        next_toc_page = None
        if i + 1 < len(valid_toc):
            next_toc_page = valid_toc[i + 1][2] - 1
        toc_title = toc_title.strip()
        content, images = extract_pdf(doc, img_prefix=img_prefix, start=toc_page, end=next_toc_page)
        chapter_list.append((toc_title, content, images))

    return chapter_list

def save_images(images, path):
    os.makedirs(f"{path}", exist_ok=True)
    debug_print("debug", f"Created folder {path} to save images")

    with console.status(f"Saving {len(images)} images to {path}..."):
        for i, (key, value) in enumerate(images.items()):
            try:
                with open(f"{path}/{key}", "wb") as f:
                    f.write(value)
            except Exception as e:
                debug_print("error", f"Error saving image {i} at {path}/{key}. Full error below.\n{e}")

def pdf_to_epub(pdf_path, output, img_prefix=""):
    global DO_SAVE_IMG, DEBUG_MODE
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        debug_print("error", f"Failed to open PDF {pdf_path}: \n{e}")
    pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0].strip()
    
    console.print()
    console.print(Rule(f"[bold white]Processing {pdf_filename}[/bold white]", style="bold white"))
    console.print()
    chapters = extract_with_toc(doc, img_prefix if img_prefix else pdf_filename)

    cover_image_name, cover_image_data = ("", "")
    try:
        cover_image_name = next(iter(chapters[0][2].keys()))
        cover_image_data = chapters[0][2][cover_image_name]
    except:
        debug_print("warning", "\nNo cover image detected")

    if DO_SAVE_IMG:
        all_images = {}
        for chapter in chapters:
            all_images.update(chapter[2])

        save_images(all_images, f"{output}/images_{pdf_filename}")
        debug_print("success", f"Saved images to {output}/images_{pdf_filename}")

    with console.status(f"Creating EPUB {output}/{pdf_filename}.epub..."):
        doc_author = doc.metadata.get("author", "")
        doc_title = doc.metadata.get("title", "").strip()
        if doc_title == "":
            doc_title = pdf_filename

        try:
            create_epub(chapters, f"{output}/{pdf_filename}.epub", doc_title, doc_author, (cover_image_name, cover_image_data))
        except Exception as e:
            debug_print("error", f"Failed to create EPUB {output}/{pdf_filename}.epub:\n{e}")

if __name__ == "__main__":
    main()
