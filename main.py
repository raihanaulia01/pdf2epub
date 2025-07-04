import pymupdf
from ebooklib import epub
import os
from rich.progress import track
from rich import print as print
from rich.pretty import pprint
import click

HEADER_FOOTER_THRESHOLD = 60
IGNORE_IMAGE_THRESHOLD = 0.7
DEBUG_MODE = False
DO_SAVE_IMG = False

@click.command()
@click.option("--input", "-i", required=True, help="Input PDF file or folder path")
@click.option("--output", "-o", default="output/", help="Output directory (default to output/)")
@click.option("--save-images", is_flag=True, help="Save extracted images from input pdf to disk")
@click.option("--header-threshold", default=60, help="Header/footer threshold for text extraction. default is 60")
@click.option("--img-threshold", default=0.7, help="Image extraction threshold. default is 0.7")
@click.option("--debug", is_flag=True, help="Enable debug mode")

# TODO edge case where the sentence is split into two pages. e.g. "test \pagebreak sentence". this won't combine properly using the current method
def main(input, output, save_images, header_threshold, img_threshold, debug):
    global HEADER_FOOTER_THRESHOLD, IGNORE_IMAGE_THRESHOLD, DEBUG_MODE, DO_SAVE_IMG
    
    HEADER_FOOTER_THRESHOLD = header_threshold
    IGNORE_IMAGE_THRESHOLD = img_threshold
    DEBUG_MODE = debug
    DO_SAVE_IMG = save_images
    
    os.makedirs(output, exist_ok=True)

    if os.path.isfile(input):
        pdf_to_epub(input, output)
    elif os.path.isdir(input):
        for filename in os.listdir(input):
            if filename.lower().endswith('.pdf'):
                pdf_path = os.path.join(input, filename)
                pdf_to_epub(pdf_path, output)
    else:
        click.echo("Error: {input} is not a valid file or directory", err=True)

def debug_print(level, text, i=None):
    global DEBUG_MODE
    if i == None:
        print_text = text
    else:
        page = i + 1
        page_debug = f"PAGE {page:3}"
        print_text = f"{page_debug:<9}: {text}"

    if level == "info":
        print(f"[grey]{print_text}[/grey]")
    elif level == "success":
        print(f"[green]{print_text}[/green]")
    elif level == "error":
        print(f"[red]{print_text}[/red]")
    elif level == "warning":
        print(f"[yellow]{print_text}[/yellow]")
    elif level == "debug" and DEBUG_MODE:
        print(f"[cyan]{print_text}[/cyan]")
    elif level == "debug_data" and DEBUG_MODE:
        pprint(text)


def create_epub(chapters, output_filename, title, author, cover_image=None):
    debug_print("info", f"\nCreating EPUB {output_filename}")
    book = epub.EpubBook()
    book.set_identifier("")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
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
    
    return text

def extract_img_from_xref(doc, xref):
    pix = pymupdf.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3: # CMYK: convert to RGB first
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix

def extract_pdf(doc: pymupdf.Document,start=0, end=None, img_prefix="", show_progress=False):
    end = doc.page_count if end == None else end
    content = ""
    images = {} # key: filename, value: image data

    page_range = range(start, end)
    if show_progress:
        page_range = track(page_range, description=f"[cyan]Processing {img_prefix}[/cyan]")

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
                if (img_bbox[1] > page_height * IGNORE_IMAGE_THRESHOLD) or in_header_footer(img_bbox, page_height): 
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
                
                debug_print("info", f"Adding image {full_img_filename}", i=i)
                images[full_img_filename] = full_img_bytes
                content += f'<img src="images/{full_img_filename}" alt="Full Image {index} on page {i+1}" />\n'

    return content, images

def extract_with_toc(doc, img_prefix):
    toc = doc.get_toc()
    chapter_list = []

    if not toc:
        debug_print("error", "Table of contents not found. This book will not have any TOC.")
        content, images = extract_pdf(doc, img_prefix=img_prefix, show_progress=True)
        return [(img_prefix, content, images)]
       
    if toc[0][2] > 1: # include the first pages that are not in the TOC
        toc.insert(0, (1, "No title", 1))

    valid_toc = [item for item in toc if item[1].strip() != ""]
    debug_print("debug_data", valid_toc)
    for i, toc_item in enumerate(track(valid_toc, description=f"[cyan]Processing chapters for {img_prefix}[/cyan]")):
        toc_lvl, toc_title, toc_page = toc_item
        toc_page -= 1  # toc is 1-based. convert to 0-based
        
        next_toc_page = None
        if i + 1 < len(valid_toc):
            next_toc_page = valid_toc[i + 1][2] - 1

        toc_title = toc_title.strip()
        content, images = extract_pdf(doc, img_prefix=img_prefix, start=toc_page, end=next_toc_page)
        chapter_list.append((toc_title, content, images))

    return chapter_list

# def pdf_to_epub(pdf_path):
#     doc = pymupdf.open(pdf_path)
#     pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
#     print(f"[bold green]{'-'*10}Processing {pdf_filename}{'-'*10}[/bold green]")
#     result = extract_pdf(doc, img_prefix=pdf_filename)

#     # save images
#     for i, (key, value) in enumerate(result[1].items()):
#         with open(f"output/images/{key}", "wb") as f:
#             f.write(value)
#     print(f"\n[green]Saved images to output/images/[/green]")

#     # save result html
#     with open(f"output/output-{pdf_filename}.html", "w", encoding="utf-8") as f:
#         f.write(result[0])
        
#     print(f"[green]Saved HTML output to output/output-{pdf_filename}.html[/green]\n")

#     chapters = [("Full book", result[0], result[1])]
#     cover_image_name = next(iter(result[1].keys()))
#     cover_image_data = result[1][cover_image_name]

#     create_epub(chapters, f"output/{pdf_filename}.epub", pdf_filename, "", (cover_image_name, cover_image_data))

def save_images(images, path):
    os.makedirs(f"{path}", exist_ok=True)
    for i, (key, value) in enumerate(images.items()):
        try:
            with open(f"{path}/{key}", "wb") as f:
                f.write(value)
        except Exception as e:
            debug_print("error", f"Error saving image {i} at {path}/{key}. Full error below.\n{e}")

def pdf_to_epub(pdf_path, output):
    global DO_SAVE_IMG, DEBUG_MODE

    doc = pymupdf.open(pdf_path)
    pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    
    print(f"[bold magenta]{'-'*10}Processing {pdf_filename}{'-'*10}[/bold magenta]")

    chapters = extract_with_toc(doc, pdf_filename)
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

        if DEBUG_MODE:
            for i, (key, value) in enumerate(all_images.items()):
                debug_print("debug", f"IMAGE {i} {key}")

        save_images(all_images, f"{output}/images_{pdf_filename}")
        debug_print("success", f"Saved images to {output}/images_{pdf_filename}")

    create_epub(chapters, f"{output}/{pdf_filename}.epub", pdf_filename, "", (cover_image_name, cover_image_data))

test_pdf_list = [
    "test_pdf/Gunatsu Volume 1.pdf",
    "test_pdf/Like Snow Piling.pdf",
    "test_pdf/What You Left Me With One Year to Live.pdf",
    "test_pdf/TomodareV1.pdf",
    "test_pdf/TomodareV2.pdf",
    "test_pdf/TomodareV3.pdf",
    "test_pdf/Kano Dere Volume 1.pdf"
]

pdf_list = [
    "D:/Light Novel/Nemotsuki/Nemotsuki Volume 1.pdf",
    "D:/Light Novel/Nemotsuki/Nemotsuki Volume 2.pdf",
    "D:/Light Novel/Nemotsuki/Nemotsuki Volume 3.pdf",
    "D:/Light Novel/Nemotsuki/Nemotsuki Volume 4.pdf",
    "D:/Light Novel/Nemotsuki/Nemotsuki Volume 5.pdf",
]

# for pdf_path in test_pdf_list:
#     pdf_to_epub(pdf_path)

if __name__ == "__main__":
    main()

print("[green]Done[/green]")