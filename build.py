import os
import glob
import json
import re
import copy
import math
from bs4 import BeautifulSoup, Comment
from urllib.parse import urljoin

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(PROJECT_ROOT, 'index.html')
BLOG_DIR = os.path.join(PROJECT_ROOT, 'blog')
SITEMAP_PATH = os.path.join(PROJECT_ROOT, 'sitemap.xml')
DOMAIN = "https://global-apple-id.top"
PAGE_SIZE = 6

class SiteBuilder:
    def __init__(self):
        self.assets = {
            'nav': None,
            'footer': None,
            'favicons': [],
            'css_js': []
        }
        self.articles_metadata = []
        self.sitemap_urls = []
        self.categories = {
            'tutorial': {'name': '新手教程', 'icon': 'fa-book-open', 'keywords': ['注册', '创建', 'Create', 'Register']},
            'billing': {'name': '充值支付', 'icon': 'fa-credit-card', 'keywords': ['充值', '礼品卡', '购买', 'Recharge', 'Redeem']},
            'troubleshoot': {'name': '故障排查', 'icon': 'fa-screwdriver-wrench', 'keywords': ['登录', '停用', '禁用', '无法', 'Login', 'Disabled', 'Lock']},
            'manage': {'name': '账号管理', 'icon': 'fa-user-gear', 'keywords': ['改区', '地区', 'Change Region', '删除', '注销', 'Delete', '密码']},
            'apps': {'name': '应用推荐', 'icon': 'fa-app-store-ios', 'keywords': ['App', '推荐', 'Software']}
        }

    def run(self):
        print("🚀 Starting build process...")
        self.step_1_extract_assets()
        self.step_2_scan_articles()
        self.step_3_process_all_pages()
        self.step_4_update_homepage()
        self.step_5_generate_sitemap()
        print("✅ Build completed successfully!")

    def read_html(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return BeautifulSoup(f, 'html.parser')

    def save_html(self, soup, path):
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        html = str(soup)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    def clean_link(self, url, current_file_path):
        if not url: return url
        if url.startswith(('http', 'https', 'mailto:', 'tel:', 'javascript:', 'data:')): return url
        
        # Resolve relative path
        if not url.startswith('/'):
            rel_path = os.path.relpath(current_file_path, PROJECT_ROOT)
            base_dir = os.path.dirname(rel_path)
            base_url_path = f"/{base_dir}/" if base_dir else "/"
            url = urljoin(base_url_path, url)
        
        if url.endswith('.html'):
            url = url[:-5]
            
        return url

    def get_category_for_article(self, title):
        for cat_slug, cat_data in self.categories.items():
            for kw in cat_data['keywords']:
                if kw.lower() in title.lower():
                    return cat_slug
        return 'tutorial' # Default

    def step_1_extract_assets(self):
        print("Phase 1: Smart Extraction from index.html...")
        soup = self.read_html(INDEX_PATH)
        self.assets['nav'] = soup.find('nav')
        self.assets['footer'] = soup.find('footer')
        
        head = soup.find('head')
        if head:
            seen_icons = set()
            for link in head.find_all('link'):
                rel = link.get('rel', [])
                if isinstance(rel, list): rel = " ".join(rel)
                if 'icon' in rel:
                    href = link.get('href', '')
                    if href and not href.startswith('http') and not href.startswith('/'):
                        href = '/' + href.lstrip('/')
                    if (href, rel) not in seen_icons:
                        link['href'] = href
                        self.assets['favicons'].append(link)
                        seen_icons.add((href, rel))

            seen_assets = set()
            def add_asset(asset):
                key = str(asset)
                if key not in seen_assets:
                    self.assets['css_js'].append(asset)
                    seen_assets.add(key)

            for s in head.find_all('script'):
                if s.get('type') != 'application/ld+json': add_asset(s)
            for l in head.find_all('link', rel=['stylesheet', 'preconnect']): add_asset(l)
            for s in head.find_all('style'): add_asset(s)

        print(f"   - Extracted Assets.")

    def step_2_scan_articles(self):
        print("Phase 2: Scanning Blog Articles...")
        files = glob.glob(os.path.join(BLOG_DIR, '*.html'))
        
        for file_path in files:
            filename = os.path.basename(file_path)
            if filename == 'index.html' or 'page' in filename: continue # Skip index and pages
            
            soup = self.read_html(file_path)
            title_tag = soup.find('title')
            raw_title = title_tag.get_text().split('|')[0].strip() if title_tag else "Untitled"
            
            # Clean Title
            clean_title = re.sub(r'[\(\[\{]?\s*202[0-9]年?\s*[\)\]\}]?', '', raw_title)
            clean_title = clean_title.replace('最新', '').replace('()', '').strip()
            
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            description = desc_tag['content'] if desc_tag else ""
            description = re.sub(r'\s*202[0-9]年?\s*', ' ', description).strip()
            
            date = "2026-01-01"
            schema = soup.find('script', type='application/ld+json')
            if schema:
                try:
                    d = json.loads(schema.string)
                    if 'datePublished' in d: date = d['datePublished']
                except: pass

            url = f"/blog/{filename.replace('.html', '')}"
            category = self.get_category_for_article(clean_title)
            
            self.articles_metadata.append({
                'title': clean_title,
                'description': description,
                'date': date,
                'url': url,
                'file_path': file_path,
                'filename': filename,
                'category': category
            })
        
        self.articles_metadata.sort(key=lambda x: x['date'], reverse=True)
        print(f"   - Found {len(self.articles_metadata)} articles.")

    def step_3_process_all_pages(self):
        print("Phase 3: Processing All Pages...")
        
        # 1. Process Individual Articles
        for article in self.articles_metadata:
            self.process_page(article['file_path'], is_article=True, meta=article)
            
        # 2. Process Blog System (Index + Pagination)
        self.generate_blog_system()
        
        # 3. Process Other Pages
        all_html = glob.glob(os.path.join(PROJECT_ROOT, '**/*.html'), recursive=True)
        processed_files = [a['file_path'] for a in self.articles_metadata]
        processed_files.append(os.path.join(BLOG_DIR, 'index.html'))
        
        for p in all_html:
            if p in processed_files or 'page' in p: continue
            self.process_page(p, is_article=False)

    def generate_blog_system(self):
        print("   - Generating Blog Pagination & Categories...")
        template_path = os.path.join(BLOG_DIR, 'index.html')
        if not os.path.exists(template_path): return
        
        base_soup = self.read_html(template_path)
        
        # Clean up existing grid
        grid_container = base_soup.find('div', class_=re.compile('grid-cols-1'))
        if grid_container: grid_container.clear()
        
        # Add Category Navigation
        self.inject_category_nav(base_soup)
        
        # Calculate Pages
        total_articles = len(self.articles_metadata)
        total_pages = math.ceil(total_articles / PAGE_SIZE)
        
        for page in range(1, total_pages + 1):
            soup = copy.copy(base_soup)
            start_idx = (page - 1) * PAGE_SIZE
            end_idx = start_idx + PAGE_SIZE
            page_articles = self.articles_metadata[start_idx:end_idx]
            
            # Populate Grid
            grid = soup.find('div', class_=re.compile('grid-cols-1'))
            for meta in page_articles:
                self.create_article_card(soup, grid, meta)
            
            # Add Pagination Controls
            self.inject_pagination(soup, page, total_pages, '/blog/')
            
            # Save
            if page == 1:
                save_path = os.path.join(BLOG_DIR, 'index.html')
                self.process_soup_assets(soup, save_path)
                self.save_html(soup, save_path)
            else:
                save_path = os.path.join(BLOG_DIR, 'page', str(page), 'index.html')
                self.process_soup_assets(soup, save_path)
                self.save_html(soup, save_path)
                
            # Add to Sitemap
            page_url = '/blog/' if page == 1 else f'/blog/page/{page}/'
            self.sitemap_urls.append({
                'loc': f"{DOMAIN}{page_url}",
                'lastmod': "2026-02-02",
                'changefreq': 'daily',
                'priority': '0.8'
            })

    def inject_category_nav(self, soup):
        header = soup.find('header')
        if not header: return
        
        # Clean up existing category navs to prevent duplication
        # 1. Remove by ID
        old_by_id = soup.find('div', id='category-nav')
        if old_by_id: old_by_id.decompose()
        
        # 2. Remove by Class (legacy cleanup)
        old_by_class = soup.find_all('div', attrs={'class': 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-8'})
        for old in old_by_class:
            old.decompose()
        
        nav_container = soup.new_tag('div', id='category-nav', attrs={'class': 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-8'})
        flex = soup.new_tag('div', attrs={'class': 'flex flex-wrap justify-center gap-3'})
        
        # 'All' button
        all_btn = soup.new_tag('a', href='/blog/', attrs={'class': 'px-5 py-2 rounded-full bg-slate-900 text-white text-sm font-bold shadow-md hover:bg-slate-800 transition'})
        all_btn.string = "All Posts"
        flex.append(all_btn)
        
        for slug, data in self.categories.items():
            btn = soup.new_tag('span', attrs={'class': 'px-5 py-2 rounded-full bg-white border border-slate-200 text-slate-600 text-sm font-bold shadow-sm hover:border-brand-300 hover:text-brand-600 transition cursor-default'})
            i = soup.new_tag('i', attrs={'class': f"fa-solid {data['icon']} mr-2 text-slate-400"})
            btn.append(i)
            btn.append(data['name'])
            flex.append(btn)
            
        nav_container.append(flex)
        header.insert_after(nav_container)

    def inject_pagination(self, soup, current, total, base_url):
        main = soup.find('main')
        if not main: return

        # Clean up existing pagination to prevent duplication
        old_by_id = soup.find('nav', id='pagination-nav')
        if old_by_id: old_by_id.decompose()
        
        old_by_class = soup.find_all('nav', attrs={'class': 'mt-16 flex justify-center gap-2'})
        for old in old_by_class:
            old.decompose()

        if total <= 1: return
        
        nav = soup.new_tag('nav', id='pagination-nav', attrs={'class': 'mt-16 flex justify-center gap-2'})
        
        # Prev
        if current > 1:
            prev_url = base_url if current == 2 else f"{base_url}page/{current-1}/"
            a = soup.new_tag('a', href=prev_url, attrs={'class': 'w-10 h-10 flex items-center justify-center rounded-lg bg-white border border-slate-200 text-slate-600 hover:border-brand-500 hover:text-brand-600 transition'})
            a.append(soup.new_tag('i', attrs={'class': 'fa-solid fa-chevron-left'}))
            nav.append(a)
            
        # Numbers
        for p in range(1, total + 1):
            is_active = (p == current)
            classes = 'w-10 h-10 flex items-center justify-center rounded-lg font-bold transition '
            classes += 'bg-slate-900 text-white shadow-lg' if is_active else 'bg-white border border-slate-200 text-slate-600 hover:border-brand-500 hover:text-brand-600'
            
            if is_active:
                span = soup.new_tag('span', attrs={'class': classes})
                span.string = str(p)
                nav.append(span)
            else:
                url = base_url if p == 1 else f"{base_url}page/{p}/"
                a = soup.new_tag('a', href=url, attrs={'class': classes})
                a.string = str(p)
                nav.append(a)
                
        # Next
        if current < total:
            next_url = f"{base_url}page/{current+1}/"
            a = soup.new_tag('a', href=next_url, attrs={'class': 'w-10 h-10 flex items-center justify-center rounded-lg bg-white border border-slate-200 text-slate-600 hover:border-brand-500 hover:text-brand-600 transition'})
            a.append(soup.new_tag('i', attrs={'class': 'fa-solid fa-chevron-right'}))
            nav.append(a)
            
        main.append(nav)

    def create_article_card(self, soup, container, meta):
        # Determine styling based on category
        cat_data = self.categories.get(meta['category'], self.categories['tutorial'])
        
        article_el = soup.new_tag('article', attrs={'class': 'bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden hover:shadow-xl hover:-translate-y-1 transition duration-300 flex flex-col h-full'})
        
        # Image Area
        bg_colors = {'tutorial': 'bg-blue-50', 'billing': 'bg-green-50', 'troubleshoot': 'bg-red-50', 'manage': 'bg-slate-100', 'apps': 'bg-purple-50'}
        icon_colors = {'tutorial': 'text-blue-300', 'billing': 'text-green-300', 'troubleshoot': 'text-red-300', 'manage': 'text-slate-400', 'apps': 'text-purple-300'}
        
        bg = bg_colors.get(meta['category'], 'bg-slate-50')
        ic = icon_colors.get(meta['category'], 'text-slate-300')
        
        a_img = soup.new_tag('a', href=meta['url'], attrs={'class': f'block h-48 {bg} relative overflow-hidden group'})
        div_icon = soup.new_tag('div', attrs={'class': 'absolute inset-0 flex items-center justify-center transition group-hover:scale-110 duration-500'})
        div_icon.append(soup.new_tag('i', attrs={'class': f"fa-solid {cat_data['icon']} text-6xl {ic}"}))
        a_img.append(div_icon)
        
        # Badge
        badge = soup.new_tag('div', attrs={'class': 'absolute top-4 left-4'})
        span = soup.new_tag('span', attrs={'class': 'bg-white/90 backdrop-blur text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider shadow-sm text-slate-800'})
        span.string = cat_data['name']
        badge.append(span)
        a_img.append(badge)
        
        article_el.append(a_img)
        
        # Content
        div_content = soup.new_tag('div', attrs={'class': 'p-6 flex-1 flex flex-col'})
        
        div_meta = soup.new_tag('div', attrs={'class': 'flex items-center gap-2 text-xs text-slate-500 mb-3'})
        div_meta.append(soup.new_tag('i', attrs={'class': 'fa-regular fa-calendar mr-1'}))
        div_meta.append(f" {meta['date']}")
        div_content.append(div_meta)
        
        h2 = soup.new_tag('h2', attrs={'class': 'text-xl font-bold text-slate-900 mb-3 leading-snug'})
        a_title = soup.new_tag('a', href=meta['url'], attrs={'class': 'hover:text-brand-600 transition'})
        a_title.string = meta['title']
        h2.append(a_title)
        div_content.append(h2)
        
        p = soup.new_tag('p', attrs={'class': 'text-slate-500 text-sm mb-6 flex-1 line-clamp-3'})
        p.string = meta['description']
        div_content.append(p)
        
        a_read = soup.new_tag('a', href=meta['url'], attrs={'class': 'text-brand-600 font-bold text-sm hover:underline mt-auto inline-flex items-center'})
        a_read.string = "Read Article "
        a_read.append(soup.new_tag('i', attrs={'class': 'fa-solid fa-arrow-right ml-1'}))
        div_content.append(a_read)
        
        article_el.append(div_content)
        container.append(article_el)

    def process_soup_assets(self, soup, file_path):
        is_index = (os.path.basename(file_path) == 'index.html' and 'blog' not in file_path)
        
        # Link Cleaning
        for a in soup.find_all('a', href=True):
            if not is_index and a['href'].startswith('#'):
                a['href'] = '/' + a['href']
            else:
                a['href'] = self.clean_link(a['href'], file_path)
            
            # Security
            if a['href'].startswith(('http', 'https')) and not a['href'].startswith(DOMAIN):
                rel = a.get('rel', [])
                if isinstance(rel, str): rel = rel.split()
                for r in ['noopener', 'nofollow', 'noreferrer']:
                    if r not in rel: rel.append(r)
                a['rel'] = rel

        # Inject Assets
        if self.assets['nav']:
            old = soup.find('nav')
            if old: old.replace_with(copy.copy(self.assets['nav']))
            elif soup.body: soup.body.insert(0, copy.copy(self.assets['nav']))

        if self.assets['footer']:
            old = soup.find('footer')
            if old: old.replace_with(copy.copy(self.assets['footer']))
            elif soup.body: soup.body.append(copy.copy(self.assets['footer']))

    def process_page(self, file_path, is_article=False, meta=None):
        soup = self.read_html(file_path)
        self.process_soup_assets(soup, file_path)
        
        if is_article and meta:
            # Reconstruct Head (Simplified for brevity, same logic as before)
            head = soup.find('head') or soup.new_tag('head')
            if not soup.find('head'): soup.insert(0, head)
            head.clear()
            
            # Meta tags
            head.append(soup.new_tag('meta', charset="utf-8"))
            head.append(soup.new_tag('meta', attrs={"name": "viewport", "content": "width=device-width, initial-scale=1.0"}))
            t = soup.new_tag('title')
            t.string = meta['title']
            head.append(t)
            head.append(soup.new_tag('meta', attrs={"name": "description", "content": meta['description']}))
            
            # OG/Twitter
            head.append(soup.new_tag('meta', attrs={"property": "og:title", "content": meta['title']}))
            head.append(soup.new_tag('meta', attrs={"property": "og:description", "content": meta['description']}))
            head.append(soup.new_tag('meta', attrs={"property": "og:url", "content": f"{DOMAIN}{meta['url']}"}))
            head.append(soup.new_tag('link', rel="canonical", href=f"{DOMAIN}{meta['url']}"))
            
            # Assets
            for icon in self.assets['favicons']: head.append(copy.copy(icon))
            for res in self.assets['css_js']: head.append(copy.copy(res))
            
            # Schema
            schema = {
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": meta['title'],
                "description": meta['description'],
                "datePublished": meta['date'],
                "author": {"@type": "Organization", "name": "Global Apple ID"}
            }
            s = soup.new_tag('script', type="application/ld+json")
            s.string = json.dumps(schema, indent=2, ensure_ascii=False)
            head.append(s)
            
            # H1 Cleaning
            h1 = soup.find('h1')
            if h1: h1.string = meta['title']

            # Recommendations
            article_tag = soup.find('article')
            if article_tag:
                rec = soup.find('div', id='recommended-reading') or soup.new_tag('div', id='recommended-reading', attrs={'class': 'mt-12 pt-8 border-t border-slate-200'})
                if not rec.parent: article_tag.append(rec)
                rec.clear()
                rec.append(soup.new_tag('h3', attrs={'class': 'text-2xl font-bold mb-6'}, string="Recommended"))
                grid = soup.new_tag('div', attrs={'class': 'grid grid-cols-1 md:grid-cols-2 gap-6'})
                count = 0
                for om in self.articles_metadata:
                    if om['filename'] == meta['filename']: continue
                    if count >= 2: break
                    
                    card = soup.new_tag('a', href=om['url'], attrs={'class': 'block bg-slate-50 p-4 rounded-xl hover:bg-white border border-slate-100 hover:shadow-md transition'})
                    h4 = soup.new_tag('h4', attrs={'class': 'font-bold text-sm mb-1'})
                    h4.string = om['title']
                    card.append(h4)
                    grid.append(card)
                    count += 1
                rec.append(grid)

        # Collect Sitemap
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        if '404' in rel_path or 'google' in rel_path or 'MasterTool' in rel_path or 'SEO_Dashboard' in rel_path:
            pass
        elif is_article and meta:
            self.sitemap_urls.append({
                'loc': f"{DOMAIN}{meta['url']}",
                'lastmod': meta['date'],
                'changefreq': 'monthly',
                'priority': '0.8'
            })
        elif not is_article and 'page' not in rel_path and 'blog/index.html' not in rel_path:
            url = '/' if rel_path == 'index.html' else f"/{rel_path.replace('.html', '')}"
            priority = '1.0' if url == '/' else '0.5'
            freq = 'daily' if url == '/' else 'monthly'
            
            self.sitemap_urls.append({
                'loc': f"{DOMAIN}{url}",
                'lastmod': '2026-02-02',
                'changefreq': freq,
                'priority': priority
            })

        self.save_html(soup, file_path)
        print(f"   > Processed {os.path.basename(file_path)}")

    def step_4_update_homepage(self):
        print("Phase 4: Global Update (Homepage)...")
        soup = self.read_html(INDEX_PATH)
        # (Simplified homepage update logic for brevity - keeping it functional)
        # Find blog section
        blog_sec = soup.find(string=re.compile("Latest Tutorials"))
        if blog_sec and blog_sec.find_parent('section'):
            grid = blog_sec.find_parent('section').find('div', class_=re.compile('grid-cols'))
            if grid:
                grid.clear()
                for meta in self.articles_metadata[:3]:
                    self.create_article_card(soup, grid, meta)
                self.save_html(soup, INDEX_PATH)

    def step_5_generate_sitemap(self):
        print("Phase 5: Generating Sitemap...")
        
        # Sort: Homepage -> Blog -> Articles -> Others
        def sitemap_sort(item):
            u = item['loc']
            if u == DOMAIN + '/': return 0
            if u == DOMAIN + '/blog/': return 1
            if '/blog/' in u and 'page' not in u: return 2 # Articles
            return 3
            
        self.sitemap_urls.sort(key=sitemap_sort)
        
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for u in self.sitemap_urls:
            xml.append(f"  <url>")
            xml.append(f"    <loc>{u['loc']}</loc>")
            xml.append(f"    <lastmod>{u['lastmod']}</lastmod>")
            xml.append(f"    <changefreq>{u['changefreq']}</changefreq>")
            xml.append(f"    <priority>{u['priority']}</priority>")
            xml.append(f"  </url>")
        xml.append('</urlset>')
        
        with open(SITEMAP_PATH, 'w', encoding='utf-8') as f: 
            f.write('\n'.join(xml))

if __name__ == "__main__":
    SiteBuilder().run()
