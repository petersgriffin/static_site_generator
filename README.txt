My personal static site generator, in Python 3.

Primarily for my local personal knowledge base, publishable to local filesystem
or a web host.

Uses standard libraries, except for Jinja for templating (to be replaced by
custom code).

Processes a directory tree of text files into a static website. Source directory
contents copied to output directory, so static files can be referenced in source
files.

Source files (those ending in .html) contain a metadata header, a configurable
delimeter sequence, and the rest of the file is for the custom page HTML and
convenience macros.

Example:

title: Example Page
tags: comma list, of, tags
date: 2022-12-12
arbitrary_field: value_available_in_template
====
<div>
Freehand HTML goes here, {{link("https://example.com/", "Example convenience
macro")}} (for when plain HTML takes too long to write)
</div>

End Example.

Prioritizes ease of adding new text files quickly, at the expense of the URLs
retaining the .html extension when hosted without URL rewriting.

Final site navigation / URL hierarchy maps to source directory structure and
internal 'page_id':
   - site_data/example.com/index.html                 = index
   - site_data/example.com/news.html                  = news
   -    output/example.com/news/current/national.html = news/current/national
   -   https://example.com/news/current/national.html  <--- published URL

Requires one index.html at site root as home page, no other index.html permitted.

Pages in a sub-directory require intermediate .html files of the same name at
the same level as the sub-directory (news.

TODOs:
 - Remove Jinja2 dependency
 - Add simple image-directory --> HTML gallery option
 - Implement Markdown for source files

No warranty, no license.
