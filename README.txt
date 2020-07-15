My personal static site generator, in Python 3.

Primarily for my local personal knowledge base, but with the secondary requirement of being publishable to a web host.

Prioritizes ease of adding new text files quickly, at the expense of the URLs retaining the .html extension when simply hosted on Amazon S3 and Google S3.

Processes a directory tree of custom-format text files into a static website.
Source directory recursively copied to output directory, including images and
other static files.

Source files (those ending in .html) contain a metadata header, a delimeter
sequence, and the rest of the file is for the custom page HTML, including
convenience macros.

Final site navigation / URL hierarchy maps to source directory structure and
internal 'page_id':
   - site_data/example.com/index.html           = index
   - site_data/example.com/news.html            = news
   -    output/example.com/news/2019/10_06.html = news/2019/10_06
   -   https://example.com/news/2019/10_06.html  <--- published URL


No warranty, no license, yet.
