import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest

# TẮT LOGGING
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger('httpx').setLevel(logging.CRITICAL)
logging.getLogger('httpcore').setLevel(logging.CRITICAL)
logging.getLogger('telegram').setLevel(logging.CRITICAL)

BOT_TOKEN = "8295420253:AAEQTwoaNEPiInqtkImPgHCMkBiKiSBRHCA"

# ============================================================
# 1. REGEX CHẶT CHẼ
# ============================================================
TARGET_URL_REGEX = r'(?:https?://)?(?:www\.)?(?:s\.lazada\.vn|c\.lazada\.vn/t/|s\.shopee\.vn)[^\s]+'

def ensure_https(url):
    return url if url.startswith(('http://', 'https://')) else 'https://' + url

def remove_https(url):
    if url.startswith('https://'): url = url[8:]
    elif url.startswith('http://'): url = url[7:]
    if '?' in url: url = url.split('?')[0]
    return url

# ============================================================
# 2. HÀM XỬ LÝ DOMAIN CHẶN (CLEAN & REMOVE)
# ============================================================
def clean_domain_input(domain):
    """Lột sạch vỏ chỉ lấy domain lõi"""
    clean = domain.lower().strip()
    clean = clean.replace("https://", "").replace("http://", "").replace("www.", "")
    if clean.endswith('/'): clean = clean[:-1]
    return clean

def remove_excluded_urls(text, excluded_domains):
    """Xóa sạch chuỗi chứa domain chặn"""
    if not excluded_domains or not text:
        return text
    
    try:
        clean_list = [clean_domain_input(d) for d in excluded_domains if d.strip()]
        
        for domain in clean_list:
            if not domain: continue
            # Regex xóa bất kể định dạng nào dính líu đến domain này
            pattern = r'(?i)\S*' + re.escape(domain) + r'\S*'
            text = re.sub(pattern, '', text)
            
        return text
    except Exception as e:
        print(f"Lỗi xóa domain: {e}")
        return text

def extract_urls_from_text(text):
    try:
        urls = re.findall(TARGET_URL_REGEX, text)
        cleaned_urls = []
        for u in urls:
            while u and u[-1] in '.,;:)!': u = u[:-1]
            if re.search(r'(s\.lazada\.vn|c\.lazada\.vn/t/|s\.shopee\.vn)', u):
                 cleaned_urls.append(ensure_https(u))
        return cleaned_urls
    except:
        return []

# === CÁC HÀM XỬ LÝ VĂN BẢN ===
def smart_split_text(text, limit=4000):
    if len(text) <= limit: return [text]
    parts = []
    while len(text) > limit:
        split_idx = text.rfind('\n', 0, limit)
        if split_idx == -1: split_idx = text.rfind(' ', 0, limit)
        if split_idx == -1: split_idx = limit
        parts.append(text[:split_idx])
        text = text[split_idx:].lstrip() 
    if text: parts.append(text)
    return parts

def escape_md(text):
    chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + c if c in chars else c for c in text)

def capitalize_first_word(text):
    try:
        lines = text.split('\n')
        result = []
        prefix_pattern = r'^(\s*)([\d]+\.|[📌⚡️🔥💥•])\s*'
        for line in lines:
            if not line.strip():
                result.append(line)
                continue
            if re.match(prefix_pattern, line.strip()):
                match = re.match(r'^(\s*)([\d]+\.|[📌⚡️🔥💥•])\s*(.*)', line)
                if match:
                    spaces, symbol, content = match.groups()
                    if not re.search(r'(shopee\.vn|lazada\.vn|SHOPEE|LAZADA)', content, re.IGNORECASE):
                        words = content.split()
                        capitalized_words = []
                        for word in words:
                            if word:
                                new_word = word[0].upper() + word[1:].lower()
                                capitalized_words.append(new_word)
                            else:
                                capitalized_words.append(word)
                        content = ' '.join(capitalized_words)
                    line = spaces + symbol + ' ' + content
            result.append(line)
        return '\n'.join(result)
    except:
        return text

def clean_text_google_sheet_style(text):
    try:
        text = re.sub(r'(https?://[^\s]+)\)', r'\1', text)
        text = capitalize_first_word(text)
        subs = [
            (":https://", ": https://"), ("◼️ Áp list:", ">> Áp List:"), ("◼️Áp list:", ">> Áp List:"),
            ("tên mã tại ô tìm kiếm:", ""), ("◼️Lưu mã tại:", ">> Lưu Tại:"), 
            ("Áp List:", "List:"), ("https://t.me/thanhsansaleshopeelazada", ""),
            ("⚠️Mua hàng Shopee, Lazada được Hoàn Tiền tại: https://thanhsansale.com", ""), 
            ("=> Hướng dẫn mua hàng Shopee Video được hoàn tiền: https://thanhsansale.com/blog/shopee-video-5", ""),
            ("=> Gửi link sản phẩm để ", ""), ("live tại: https://forms.gle/s8CHma2pgDyYHu5w7", ""), ("◼️ Lưu mã tại:", ">>Lưu Tại:"),
            ("=> Lưu mã tại:", ">>Lưu Tại:"), ("=>", ">>"), ("◼️Chi tiết:", ">>Chi Tiết:"), ("◼️ Chi tiết:", ">>Chi Tiết:"),
            (" cho đơn từ ", "/"), ("000000", "tr"), ("00000", "00k"),
            (".000đ", "k"), ("giảm tối đa", "giảm"), (".000.000Đ", "tr"), ("tối đa", "max"), (" cho đơn hàng hợp lệ từ ", "/"),
            (" cho đơn hàng tối thiểu ", "/"), ("- G", "g"), (" đơn từ ", "/"), (" đơn ", "/"), ("◼️", "-"), ("►", "-"), ("•", "-"),
            ("✦", "-"), ("➥", "-"), ("⚡️", "📌"), ("🔳", "📌"), ("- 0H: 0h: ", "- 0H: "), ("- 0h: 0h: ", "- 0H: "),
            (", xem tên mã tại: ", ": "), ("Lưu dùng luôn ", ""), ("Dùng luôn: ", ""), ("📍", "📌"), ("cho list sp", "List"),
            ("* Mã ", "- 0h: "), (". List sản phẩm áp mã: ", " List: "), ("🔥", "📌"), ("cho list sp:", "List:"), ("áp list sp:", "List:"),
            ("áp list:", "List:"), ("Áp list:", "List:"), ("tặng sẵn", "Sẵn Ví"), ("🔺 ", "📌"), ("Official Store", ""), ("Official", ""),
            ("Chính Hãng", ""), ("(", ""), (")", ""), ("cho shop", "shop"), ("chính hãng", ""), ("Vietnam", ""), (" từ ", "/"),
            (" OFFICIAL", ""), (" STORE", ""), ("✨", "📌"), ("Xem tên mã tại ô tìm kiếm:", "ô tìm kiếm:"), ("●", "-"), ("Tặng sẵn ", ""),
            ("back vào 9H, 12H, 15H, 18H, 21H", ""), ("Đặt lịch tag live dùng mã live: https://www.facebook.com/taglivebuichung hoặc https://t.me/tagvideo_bot", ""),
            ("Đặt lịch live", ""), ("https://www.facebook.com/taglivebuichung", ""), (" Đơn ", "/"), ("TỐI ĐA", "max"), (" từ ", "/"),
            ("https://mycollection.shop/thanhsansale", "")
        ]
        for old, new in subs:
            text = text.replace(old, new)
        return text
    except:
        return text

def generate_telegram_format(text):
    try:
        exclude = {'SHOPEE', 'LAZADA', 'VIDEO', 'LIST', 'LIVE'}
        urls = set(re.findall(TARGET_URL_REGEX, text))
        lines = text.split('\n')
        final_lines = []
        header_pattern = r'^(\d+\.|📌|⚡️|💥|🔥|🔔|🔺|🔸|▪️|•)'
        for line in lines:
            if not line.strip():
                final_lines.append("")
                continue
            header_part = ""
            body_part = line
            is_header = False
            if re.match(header_pattern, line.strip()):
                pos = line.find(':')
                if pos != -1:
                    header_raw = line[:pos+1]
                    body_raw = line[pos+1:]
                    header_part = f"*{escape_md(header_raw)}*"
                    body_part = body_raw
                    is_header = True
                else:
                    header_part = f"*{escape_md(line)}*"
                    body_part = "" 
                    is_header = True
            if not is_header:
                body_part = line
                header_part = ""
            codes_found = []
            def replace_code(match):
                word = match.group(0)
                if len(word) < 3: return word
                uppercase_count = sum(1 for c in word if c.isalpha() and c.isupper())
                if uppercase_count < 3: return word
                start = match.start()
                context = body_part[max(0, start-30):match.end()+30]
                if any(u in context for u in urls): return word
                if word in exclude: return word
                placeholder = f"zzCODEMARKER{len(codes_found)}zz"
                codes_found.append(word)
                return placeholder
            body_processed = re.sub(r'\b[A-Za-z0-9]+\b', replace_code, body_part)
            body_escaped = escape_md(body_processed)
            for i, code in enumerate(codes_found):
                formatted_code = f"`{escape_md(code)}`"
                body_escaped = body_escaped.replace(f"zzCODEMARKER{i}zz", formatted_code)
            final_lines.append(header_part + body_escaped)
        return '\n'.join(final_lines)
    except:
        return escape_md(text)

def convert_prefix_style(text, target_style):
    try:
        lines = text.split('\n')
        result = []
        count = 1
        pattern = r'^(\s*)(\d+\.|[📌⚡️🔥💥])\s*'
        for line in lines:
            if re.match(pattern, line.strip()):
                match = re.match(r'^(\s*)(\d+\.|[📌⚡️🔥💥])\s*(.*)', line)
                if match:
                    indent, old_symbol, content = match.groups()
                    if target_style == "number":
                        new_prefix = f"{count}."
                        count += 1
                    else:
                        new_prefix = target_style
                    line = f"{indent}{new_prefix} {content}"
            result.append(line)
        return '\n'.join(result)
    except:
        return text

def adjust_line_spacing(text, mode="thu"):
    try:
        lines = text.split('\n')
        result = []
        if mode == "thu":
            result = [l for l in lines if l.strip()]
        elif mode == "cach":
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if not line_stripped:
                    result.append(line)
                    continue
                if line_stripped == ".":
                    if result and result[-1].strip() != "": result.extend(["", ""])
                    result.append(line)
                else:
                    result.append(line)
                    if (i < len(lines) - 1 and lines[i + 1].strip() != "" and lines[i + 1].strip() != "."):
                        result.append("")
        return '\n'.join(result)
    except: return text

def replace_urls_in_text(orig, new_urls):
    try:
        cleaned = clean_text_google_sheet_style(orig)
        current_urls_in_cleaned = re.findall(TARGET_URL_REGEX, cleaned)
        clean_found_urls = []
        for u in current_urls_in_cleaned:
             while u and u[-1] in '.,;:)!': u = u[:-1]
             if re.search(r'(s\.lazada\.vn|c\.lazada\.vn/t/|s\.shopee\.vn)', u):
                clean_found_urls.append(u)
        for old_url_in_text, new_url_input in zip(clean_found_urls, new_urls):
            replacement_url = remove_https(new_url_input)
            cleaned = cleaned.replace(old_url_in_text, replacement_url, 1)
        return cleaned
    except: return orig

def is_url_list(text):
    try:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return len(lines) > 0 and sum(1 for l in lines if l.startswith('http')) / len(lines) >= 0.5
    except: return False

def extract_urls_from_list(text):
    try: return [l.strip() for l in text.split('\n') if l.strip().startswith('http')]
    except: return []

# === KEYBOARDS ===
def get_action_keyboard():
    keyboard = [
        [InlineKeyboardButton("🧹 Thu gọn", callback_data="cmd_thu"), InlineKeyboardButton("↔️ Cách dòng", callback_data="cmd_cach")],
        [InlineKeyboardButton("🔢 1.2.3", callback_data="convert_number"), InlineKeyboardButton("💥 Boom", callback_data="convert_boom"), InlineKeyboardButton("⚡️ Flash", callback_data="convert_flash"), InlineKeyboardButton("📌 Pin", callback_data="convert_pin")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_clear_memory_keyboard():
    keyboard = [[InlineKeyboardButton("🗑 Xóa văn bản (Giữ lại /d)", callback_data="cmd_clear_memory")]]
    return InlineKeyboardMarkup(keyboard)

# === LỆNH /d: THÊM DOMAIN ===
async def add_domain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        current_list = context.user_data.get('excluded_domains', set())
        display_list = [clean_domain_input(d) for d in current_list if d.strip()]
        if display_list:
            msg = "📋 *Danh sách tên miền đang bị chặn:*\n" + "\n".join(f"- `{d}`" for d in display_list)
        else:
            msg = "ℹ️ Danh sách chặn đang trống.\nDùng lệnh `/d domain.com` để thêm."
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    new_domains = set()
    for arg in context.args:
        clean = clean_domain_input(arg)
        if clean:
            new_domains.add(clean)

    current_list = context.user_data.get('excluded_domains', set())
    current_list.update(new_domains)
    context.user_data['excluded_domains'] = current_list
    
    await update.message.reply_text(f"✅ Đã thêm {len(new_domains)} domain.\nBot sẽ xóa toàn bộ link chứa các domain này.")

# === LOGIC XỬ LÝ CHÍNH ===
async def process_buffer_logic(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    text_parts = context.user_data.get('msg_buffer', [])
    context.user_data['msg_buffer'] = [] 
    if not text_parts: return
    full_text = "\n".join(text_parts)
    
    try:
        if is_url_list(full_text):
            original_text = context.user_data.get('original_text', "")
            if not original_text:
                await context.bot.send_message(chat_id, "⚠️ Chưa có văn bản gốc. Vui lòng gửi văn bản nội dung trước.")
                return
            
            new_urls = extract_urls_from_list(full_text)
            final_raw = replace_urls_in_text(original_text, new_urls)
            
            # LỌC DOMAIN CUỐI CÙNG
            excluded_domains = context.user_data.get('excluded_domains', set())
            final_raw = remove_excluded_urls(final_raw, excluded_domains)
            
            context.user_data['working_text'] = final_raw
            context.user_data['bot_msg_ids'] = []

            formatted = generate_telegram_format(final_raw)
            chunks = smart_split_text(formatted)
            
            for i, chunk in enumerate(chunks):
                markup = get_action_keyboard() if i == len(chunks) - 1 else None
                msg = await context.bot.send_message(chat_id, chunk, parse_mode='MarkdownV2', reply_markup=markup)
                context.user_data['bot_msg_ids'].append(msg.message_id)
            
            await context.bot.send_message(chat_id, "✅ Đã xử lý xong.", reply_markup=get_clear_memory_keyboard())
                
        else:
            urls = extract_urls_from_text(full_text)
            if urls:
                current_text = context.user_data.get('original_text', "")
                context.user_data['original_text'] = (current_text + "\n" + full_text) if current_text else full_text
                
                urls_text = "\n".join(urls)
                await context.bot.send_message(chat_id, f"⬇️ Đã lưu phần văn bản.\nLink tìm thấy (Chỉ Shopee/Lazada):\n{urls_text}\n\n👉 Gửi tiếp hoặc gửi List Link để hoàn tất.", reply_markup=get_clear_memory_keyboard()) 
            else:
                excluded_domains = context.user_data.get('excluded_domains', set())
                cleaned_text = remove_excluded_urls(full_text, excluded_domains)
                
                context.user_data['working_text'] = clean_text_google_sheet_style(cleaned_text)
                context.user_data['bot_msg_ids'] = []
                
                formatted = generate_telegram_format(context.user_data['working_text'])
                chunks = smart_split_text(formatted)
                
                for i, chunk in enumerate(chunks):
                    markup = get_action_keyboard() if i == len(chunks) - 1 else None
                    msg = await context.bot.send_message(chat_id, chunk, parse_mode='MarkdownV2', reply_markup=markup)
                    context.user_data['bot_msg_ids'].append(msg.message_id)

    except Exception as e:
        print(f"Error: {e}")
        try:
            await context.bot.send_message(chat_id, "❌ Lỗi xử lý: Có thể do định dạng quá phức tạp.")
        except: pass

# === HANDLER TIN NHẮN ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if not msg or msg.startswith('/'): return
    chat_id = update.effective_chat.id

    if 'msg_buffer' not in context.user_data: context.user_data['msg_buffer'] = []
    context.user_data['msg_buffer'].append(msg)

    if 'debounce_task' in context.user_data:
        task = context.user_data['debounce_task']
        if not task.done(): task.cancel()
    
    async def delayed_run():
        try:
            await asyncio.sleep(4.0)
            await process_buffer_logic(chat_id, context)
        except asyncio.CancelledError: pass

    context.user_data['debounce_task'] = asyncio.create_task(delayed_run())

# === HANDLER NÚT BẤM (ĐÃ SỬA LỖI XÓA NHẦM /d) ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cmd = query.data
    chat_id = query.message.chat_id

    if cmd == "cmd_clear_memory":
        # 1. Lưu lại danh sách chặn
        saved_domains = context.user_data.get('excluded_domains', set())
        
        # 2. Xóa sạch bộ nhớ
        context.user_data.clear()
        
        # 3. Khôi phục danh sách chặn
        if saved_domains:
            context.user_data['excluded_domains'] = saved_domains

        await query.edit_message_text("🗑 Đã xóa văn bản cũ (Vẫn giữ danh sách chặn /d).")
        return

    working_text = context.user_data.get('working_text', "")
    if not working_text:
        working_text = query.message.text
    
    excluded_domains = context.user_data.get('excluded_domains', set())
    working_text = remove_excluded_urls(working_text, excluded_domains)
    
    processed_text = working_text

    if cmd == "cmd_thu": processed_text = adjust_line_spacing(working_text, "thu")
    elif cmd == "cmd_cach": processed_text = adjust_line_spacing(working_text, "cach")
    elif cmd == "convert_number": processed_text = convert_prefix_style(working_text, "number")
    elif cmd == "convert_boom": processed_text = convert_prefix_style(working_text, "💥")
    elif cmd == "convert_flash": processed_text = convert_prefix_style(working_text, "⚡️")
    elif cmd == "convert_pin": processed_text = convert_prefix_style(working_text, "📌")
    
    context.user_data['working_text'] = processed_text
    formatted_full = generate_telegram_format(processed_text)

    msg_ids = context.user_data.get('bot_msg_ids', [])
    chunks = smart_split_text(formatted_full)
    
    for i, chunk_text in enumerate(chunks):
        if i < len(msg_ids):
            msg_id = msg_ids[i]
            try:
                reply_markup = get_action_keyboard() if i == len(chunks) - 1 else None
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=chunk_text,
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
            except BadRequest as e:
                if "Message is not modified" in str(e): pass
                else: print(f"Edit error: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lệnh start thì cho xóa hết để reset cứng
    context.user_data.clear()
    await update.message.reply_text("Bot sẵn sàng!\n- Gửi văn bản.\n- Dùng `/d domain` để chặn link.")

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(60).write_timeout(60).connect_timeout(60).pool_timeout(60)
        .build()
    )
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("d", add_domain_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot running (Fixed Memory Logic)...")
    app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
