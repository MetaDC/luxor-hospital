#!/usr/bin/env python3
import os
import re
import sys
import argparse
import calendar
from datetime import date

def make_slug(title):
    # Remove the "Blog N - " prefix if it is there
    title = re.sub(r'^Blog\s+\d+\s*-\s*', '', title, flags=re.IGNORECASE)
    # Remove apostrophes and quotes
    title = title.replace('“', '').replace('”', '').replace('’', '').replace("'", "")
    title = title.replace('"', '').replace('&amp;', 'and').replace('&', 'and')
    # Replace non-alphanumeric with hyphens
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '-', title)
    # Lowercase
    slug = slug.lower()
    # Replace multiple spaces/hyphens with single hyphen
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def get_distributed_dates(year, month_num, n_blogs):
    _, num_days = calendar.monthrange(year, month_num)
    if n_blogs == 1:
        return [date(year, month_num, num_days)]
    dates = []
    interval = (num_days - 1) / (n_blogs - 1)
    for i in range(n_blogs):
        day = 1 + int(round(i * interval))
        day = min(max(day, 1), num_days)
        dates.append(date(year, month_num, day))
    return dates

def parse_body_to_html(body_lines):
    html_parts = []
    in_list = False
    current_paragraph = []
    
    def flush_paragraph():
        nonlocal current_paragraph
        if current_paragraph:
            text = " ".join(current_paragraph).strip()
            text = re.sub(r'\s+', ' ', text)
            html_parts.append(f"<p><span>{text}</span></p>")
            current_paragraph = []
            
    def flush_list():
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
            
        # Check for bullet item
        bullet_match = re.match(r'^[●\-\*]\s*(.*)', stripped)
        if bullet_match:
            flush_paragraph()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item_text = bullet_match.group(1).strip()
            html_parts.append(f"<li><span>{item_text}</span></li>")
            continue
            
        # Check for numbered item
        num_match = re.match(r'^\d+\.\s*(.*)', stripped)
        if num_match:
            flush_paragraph()
            flush_list()
            header_text = num_match.group(1).strip()
            html_parts.append(f"<h3><span>{header_text}</span></h3>")
            continue
            
        # Check for subheading
        # Short line, no period/colon/comma at end, and not a list item
        if (len(stripped) <= 60 and 
            not stripped.endswith('.') and 
            not stripped.endswith('!') and
            not stripped.endswith(':') and
            not stripped.endswith(',') and
            (stripped.endswith('?') or not stripped[-1].isalnum() or re.match(r'^[A-Z]', stripped))):
            
            flush_paragraph()
            flush_list()
            html_parts.append(f'<h2><span><font color="#ac8f5a">{stripped}</font></span></h2>')
            continue
            
        # Otherwise, regular paragraph text
        flush_list()
        current_paragraph.append(stripped)
        
    flush_paragraph()
    flush_list()
    return "\n".join(html_parts)

def extract_existing_blogs_from_html(blog_html_content):
    existing_blogs_in_html = []
    # Pattern to find blog cards inside blog.html
    card_pattern = re.compile(
        r'<div class="col-xl-4 col-lg-4[^>]*>\s*<a\s+href="blogs/(?P<slug>[^"]+)\.html"[^>]*>.*?<img\s+src="(?P<img_src>[^"]+)"[^>]*>.*?<h3 class="blog-one__title">\s*<a[^>]*>(?P<title>.*?)</a\s*>\s*</h3\s*>.*?<span class="blog-block__meta">(?P<date>[^<]+)</span\s*>',
        re.DOTALL
    )
    for match in card_pattern.finditer(blog_html_content):
        # Normalize whitespace in the title
        title_clean = re.sub(r'\s+', ' ', match.group('title')).strip()
        existing_blogs_in_html.append({
            'slug': match.group('slug'),
            'img_src': match.group('img_src'),
            'title': title_clean,
            'date': match.group('date').strip()
        })
    return existing_blogs_in_html

def format_sidebar_img_src(img_src):
    if img_src.startswith('http'):
        return img_src
    if not img_src.startswith('../'):
        return '../' + img_src
    return img_src

def replace_sidebar_sides(html, sidebar_html):
    start_match = re.search(r'<div\s+class="sidebar__sides"\s+id="blog-sides"[^>]*>', html)
    if not start_match:
        return html
    start_pos = start_match.start()
    
    stop_match = re.search(r'<div\s+class="sidebar__tags-wrapper\s+sidebar__single"[^>]*>', html)
    if not stop_match:
        stop_match = re.search(r'<div\s+class="sidebar__tags-wrapper', html)
        
    if not stop_match:
        return html
    stop_pos = stop_match.start()
    
    replacement = f"""<div class="sidebar__sides" id="blog-sides">
{sidebar_html}
                    </div>
                    <!-- /.sidebar__title -->
                  </div>
                  <!-- /.sidebar__posts-wrapper sidebar__single -->

                  """
    return html[:start_pos] + replacement + html[stop_pos:]

def get_tags_for_title(title):
    words = re.sub(r'[^\w\s-]', '', title).split()
    stop_words = {'vs', 'and', 'or', 'to', 'the', 'a', 'for', 'in', 'of', 'with', 'how', 'why', 'on', 'at', 'by', 'an', 'is', 'what', 'doesnt', 'options', 'key', 'differences', 'treatment', 'approach', 'myths', 'social', 'media', 'most', 'popular', 'treatments', 'works', 'does'}
    filtered = [w for w in words if w.lower() not in stop_words]
    tags = []
    for word in filtered[:3]:
        if len(word) > 3:
            tags.append(word.capitalize())
    if not tags:
        tags = ['Health', 'Treatment']
    return tags

def parse_all_blogs_from_md(md_path):
    if not os.path.exists(md_path):
        print(f"Error: Markdown file not found at {md_path}")
        sys.exit(1)
        
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Split content by lines
    lines = content.split('\n')
    
    blogs = []
    current_blog = None
    
    for line in lines:
        match = re.match(r'^\s*Blog\s+(\d+)\s*-\s*(.*)', line)
        if match:
            if current_blog:
                blogs.append(current_blog)
            current_blog = {
                'number': int(match.group(1)),
                'title_lines': [match.group(2).strip()],
                'body_lines': [],
                'raw_lines': [line]
            }
        elif current_blog:
            current_blog['body_lines'].append(line)
            current_blog['raw_lines'].append(line)
            
    if current_blog:
        blogs.append(current_blog)
        
    # Post-process titles and body lines
    for blog in blogs:
        body_lines = blog['body_lines']
        title_lines = blog['title_lines']
        
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
            
        while body_lines:
            first_line = body_lines[0].strip()
            if not first_line:
                break
            if first_line.lower() == 'introduction':
                break
            title_lines.append(first_line)
            body_lines.pop(0)
                
        blog['title'] = " ".join(title_lines).replace("–", "-").strip()
        blog['title'] = re.sub(r'\s+', ' ', blog['title'])
        blog['slug'] = make_slug(blog['title'])
        
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
            
    return blogs

def main():
    parser = argparse.ArgumentParser(description="Luxor Hospital Blog Automator")
    default_source = 'blogs.md' if os.path.exists('blogs.md') else 'all.md'
    parser.add_argument('--source', default=default_source, help='Source markdown file')
    parser.add_argument('--template', default='blogs/dry-eye-syndrome-causes-treatment-when-to-see-an-eye-specialist.html', help='Template HTML page')
    parser.add_argument('--month', help='Target month name (e.g. July)')
    parser.add_argument('--year', type=int, help='Target year (e.g. 2026)')
    parser.add_argument('--start', type=int, help='Only add blogs starting from this blog number')
    args = parser.parse_args()
    
    # 1. Parse blogs from source markdown
    print(f"Parsing blogs from {args.source}...")
    all_blogs = parse_all_blogs_from_md(args.source)
    print(f"Found {len(all_blogs)} total blogs in markdown.")
    
    # 2. Read existing slugs from linked_blogs.txt
    linked_blogs_path = 'linked_blogs.txt'
    existing_slugs = []
    if os.path.exists(linked_blogs_path):
        with open(linked_blogs_path, 'r', encoding='utf-8') as f:
            existing_slugs = [line.strip() for line in f if line.strip()]
    print(f"Found {len(existing_slugs)} existing linked blogs.")
    
    # 3. Filter for new blogs
    new_blogs = [b for b in all_blogs if b['slug'] not in existing_slugs]
    if args.start is not None:
        new_blogs = [b for b in new_blogs if b['number'] >= args.start]
    if not new_blogs:
        print("No new blogs found to link. Everything is up to date!")
        return
        
    print(f"\nFound {len(new_blogs)} new blogs to add:")
    for b in new_blogs:
        print(f"  - Blog {b['number']}: {b['title']} (slug: {b['slug']})")
        
    # 4. Determine target month and year
    month_name = args.month
    year = args.year
    
    # Simple month mapping
    months_map = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
    
    if not month_name or not year:
        # Auto-detect or fallback
        # Let's read blog.html to see what the latest date is
        blog_html_path = 'blog.html'
        latest_month = "July"
        latest_year = 2026
        if os.path.exists(blog_html_path):
            with open(blog_html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            parsed_blogs = extract_existing_blogs_from_html(html_content)
            if parsed_blogs:
                # E.g. "June 30 2026"
                latest_date_str = parsed_blogs[0]['date']
                date_parts = latest_date_str.split()
                if len(date_parts) == 3:
                    m_str, _, y_str = date_parts
                    try:
                        latest_year = int(y_str)
                        m_num = months_map.get(m_str.lower(), 6)
                        # Increment month
                        if m_num == 12:
                            latest_month = "January"
                            latest_year += 1
                        else:
                            latest_month = calendar.month_name[m_num + 1]
                    except Exception as e:
                        pass
        
        if not month_name:
            if sys.stdin.isatty():
                val = input(f"Enter target month [{latest_month}]: ").strip()
                month_name = val if val else latest_month
            else:
                month_name = latest_month
        if not year:
            if sys.stdin.isatty():
                val = input(f"Enter target year [{latest_year}]: ").strip()
                year = int(val) if val else latest_year
            else:
                year = latest_year
                
    month_num = months_map.get(month_name.lower())
    if not month_num:
        print(f"Error: Invalid month name '{month_name}'")
        sys.exit(1)
        
    print(f"\nAdding {len(new_blogs)} blogs for {month_name} {year}...")
    
    # 5. Get distributed dates
    dates = get_distributed_dates(year, month_num, len(new_blogs))
    
    # 6. Read template HTML file
    if not os.path.exists(args.template):
        print(f"Error: Template file not found at {args.template}")
        sys.exit(1)
    with open(args.template, 'r', encoding='utf-8') as f:
        template_content = f.read()
        
    # 7. Read existing blog.html content
    blog_html_path = 'blog.html'
    if not os.path.exists(blog_html_path):
        print(f"Error: blog.html not found at {blog_html_path}")
        sys.exit(1)
    with open(blog_html_path, 'r', encoding='utf-8') as f:
        blog_html_content = f.read()
        
    # Get top 3 existing blogs for sidebar from the start
    recent_blogs = extract_existing_blogs_from_html(blog_html_content)[:3]
    print("Top 3 recent blogs for sidebar:")
    for rb in recent_blogs:
        print(f"  - {rb['title']} ({rb['date']})")
        
    # Format Other Blogs sidebar HTML
    sidebar_parts = []
    for rb in recent_blogs:
        sidebar_img = format_sidebar_img_src(rb['img_src'])
        sidebar_parts.append(f"""                      <div class="blog-block blog-block--style6 mb-25">
                        <div class="blog-block__img">
                          <a
                            class="blog-block__img__link"
                            href="{rb['slug']}.html"
                          >
                            <img
                              class="rounded-2"
                              src="{sidebar_img}"
                              alt="Blog"
                              style="
                                width: 90px;
                                height: 90px;
                                object-fit: cover;
                              "
                            />
                          </a>
                        </div>
                        <div class="blog-block__content">
                          <span class="blog-block__meta">{rb['date']}</span>
                          <h4 class="blog-block__heading mb-0">
                            <a
                              href="{rb['slug']}.html"
                              style="font-size: 18px; color: grey"
                            >
                              {rb['title']}
                            </a>
                          </h4>
                        </div>
                      </div>""")
    sidebar_html = "\n\n".join(sidebar_parts)
    
    # 8. Generate files and cards
    new_cards = []
    markdown_append_parts = []
    
    # Sort new blogs ascending so the latest one gets the latest date
    new_blogs_sorted = sorted(new_blogs, key=lambda b: b['number'])
    
    for idx, blog in enumerate(new_blogs_sorted):
        b_date = dates[idx]
        date_str = b_date.strftime("%b %d %Y")
        # Ensure single digits have leading zero
        m_str, d_str, y_str = date_str.split()
        if len(d_str) == 1:
            d_str = "0" + d_str
        date_str = f"{m_str} {d_str} {y_str}"
        
        slug = blog['slug']
        number = blog['number']
        title = blog['title']
        body_html = parse_body_to_html(blog['body_lines'])
        
        # A. Generate the blog page HTML
        print(f"Generating page for Blog {number}: {title}...")
        page_html = template_content
        
        # Replace title
        page_html = re.sub(r'<title>.*?</title>', f'<title>{title} | Luxor Hospital</title>', page_html, flags=re.DOTALL)
        # Replace og:title
        page_html = re.sub(r'<meta\s+property="og:title"\s+content="[^"]*"\s*/?>', f'<meta property="og:title" content="{title}" />', page_html, flags=re.DOTALL)
        # Replace page-header title
        page_html = re.sub(r'<h2 class="page-header__title">.*?</h2>', f'<h2 class="page-header__title">\n            {title}\n          </h2>', page_html, flags=re.DOTALL)
        # Replace blog-thumb image src
        page_html = re.sub(
            r'(id="blog-thumb"[^>]*>\s*<img[^>]+src=")[^"]+("[^>]*>)',
            r'\1' + f'../assets/images/blog/{number}.webp' + r'\2',
            page_html,
            flags=re.DOTALL
        )
        # Replace page-header background image style
        page_html = re.sub(
            r'(\.page-header__bg\s*\{\s*background-image:\s*url\()[^)]+(\)\s*!important;\s*\})',
            r'\1' + f'../assets/images/blog/{number}.webp' + r'\2',
            page_html,
            flags=re.DOTALL
        )
        # Replace date
        page_html = re.sub(r'<span\s+class="blog-block__meta"[^>]*id="blog-date"[^>]*>.*?</span\s*>', f'<span class="blog-block__meta" id="blog-date">{date_str}</span>', page_html, flags=re.DOTALL)
        # Replace title link
        page_html = re.sub(r'<h3\s+class="blog-card__title"[^>]*id="blog-title"[^>]*>.*?</h3\s*>', f'<h3 class="blog-card__title" id="blog-title"><a href="#">{title}</a></h3>', page_html, flags=re.DOTALL)
        # Replace content
        page_html = re.sub(r'<div id="blog-content">.*?</div>\s*<div class="share-container">', f'<div id="blog-content">\n{body_html}\n                  </div>\n                  <div class="share-container">', page_html, flags=re.DOTALL)
        # Replace sidebar other blogs
        page_html = replace_sidebar_sides(page_html, sidebar_html)
        # Replace tags
        tags = get_tags_for_title(title)
        tags_html = "".join([f"<a>{tag}</a>" for tag in tags])
        page_html = re.sub(r'<div class="sidebar__tags"\s+id="blog-tags">.*?</div>', f'<div class="sidebar__tags" id="blog-tags">\n                      {tags_html}\n                    </div>', page_html, flags=re.DOTALL)
        
        # Write files in blogs/
        out_page_path = f"blogs/{slug}.html"
        with open(out_page_path, 'w', encoding='utf-8') as f:
            f.write(page_html)
            
        # B. Format the blog card for blog.html
        card_html = f"""            <div class="col-xl-4 col-lg-4 wow fadeInUp" data-wow-delay="100ms">
              <a
                href="blogs/{slug}.html"
                class="blog-card__link"
              >
                <div class="blog-one__single">
                  <div class="blog-one__img aspect-ratio-16-9">
                    <img src="assets/images/blog/{number}.webp" alt="Blog" />
                  </div>
                  <div class="blog-one__content">
                    <h3 class="blog-one__title">
                      <a
                        href="blogs/{slug}.html"
                        >{title}</a
                      >
                    </h3>
                    <div class="blog-card-bottom">
                      <span class="blog-card__link__back"
                        ><span class="icon-duble-arrow"></span>Read More</span
                      >
                      <span class="blog-block__meta">{date_str}</span>
                    </div>
                  </div>
                </div>
              </a>
            </div>"""
        new_cards.append(card_html)
        
        # C. Format markdown for blogs.md
        markdown_append_parts.append("\n" + "\n".join(blog['raw_lines']) + "\n")
        
    # 9. Insert cards into blog.html
    # We want to order them descending in blog.html, so we reverse the ascending list
    new_cards_desc = list(reversed(new_cards))
    cards_html_block = "\n\n".join(new_cards_desc)
    
    month_prefix = f"<!-- {month_name.lower()}blogs start -->"
    month_suffix = f"<!-- {month_name.lower()}blogs end -->"
    
    if month_prefix in blog_html_content:
        print(f"Appending cards to existing {month_name} block in blog.html...")
        idx = blog_html_content.find(month_prefix) + len(month_prefix)
        blog_html_content = blog_html_content[:idx] + "\n" + cards_html_block + blog_html_content[idx:]
    else:
        print(f"Creating new {month_name} block in blog.html...")
        list_container = 'id="blogs-list"'
        container_idx = blog_html_content.find(list_container)
        if container_idx == -1:
            print("Error: Could not find id=\"blogs-list\" in blog.html")
            sys.exit(1)
            
        comment_idx = blog_html_content.find("<!--", container_idx)
        if comment_idx == -1:
            search_str = '<div class="row gutter-y-30" id="blogs-list">'
            insert_pos = blog_html_content.find(search_str) + len(search_str)
            new_block = f"\n            {month_prefix}\n{cards_html_block}\n            {month_suffix}\n"
            blog_html_content = blog_html_content[:insert_pos] + new_block + blog_html_content[insert_pos:]
        else:
            line_start_idx = blog_html_content.rfind("\n", 0, comment_idx)
            if line_start_idx == -1:
                line_start_idx = comment_idx
            else:
                line_start_idx += 1
            new_block = f"            {month_prefix}\n{cards_html_block}\n            {month_suffix}\n\n"
            blog_html_content = blog_html_content[:line_start_idx] + new_block + blog_html_content[line_start_idx:]
            
    with open(blog_html_path, 'w', encoding='utf-8') as f:
        f.write(blog_html_content)
    print("Updated blog.html.")
    
    # 10. Update linked_blogs.txt
    print("Updating linked_blogs.txt...")
    with open(linked_blogs_path, 'a', encoding='utf-8') as f:
        for blog in new_blogs_sorted:
            f.write(blog['slug'] + '\n')
            
    # 11. Append to blogs.md
    if args.source != 'blogs.md':
        blogs_md_path = 'blogs.md'
        print("Appending to blogs.md...")
        with open(blogs_md_path, 'a', encoding='utf-8') as f:
            for part in markdown_append_parts:
                f.write(part)
            
    print("\nSuccessfully added all new blogs!")

if __name__ == '__main__':
    main()
