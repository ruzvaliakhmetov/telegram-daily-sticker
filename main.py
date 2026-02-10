import os
import random
from pathlib import Path
from datetime import datetime, date

from PIL import Image, ImageDraw, ImageFont
from zoneinfo import ZoneInfo

from telegram import Bot, InputSticker
from telegram.error import BadRequest


# Сколько всего базовых картинок есть в папке images
# (sticker512x512_01.png ... sticker512x512_XX.png)
IMAGE_COUNT = 5  # <-- поставь нужное количество

# Дата, от которой считаем дни
START_DATE = date(2026, 2, 11)


def calculate_days() -> int:
    """Сколько дней прошло с START_DATE (31 марта = 1, 1 апреля = 2 и т.д.)."""
    today = datetime.now(ZoneInfo("Europe/Stockholm")).date()
    delta = (today - START_DATE).days
    return delta + 1


def get_random_base_image_path() -> Path:
    """
    Выбираем случайную картинку по номеру от 1 до IMAGE_COUNT.
    Имя вида sticker512x512_01.png, sticker512x512_02.png и т.п.
    """
    images_dir = Path(__file__).parent / "images"

    if IMAGE_COUNT <= 0:
        raise ValueError("IMAGE_COUNT must be > 0")

    idx = random.randint(1, IMAGE_COUNT)
    filename = f"sticker512x512_{idx:02d}.png"  # 01, 02, ..., 09, 10, ...
    path = images_dir / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Base image not found: {path}. "
            f"Check that IMAGE_COUNT={IMAGE_COUNT} matches files in {images_dir}"
        )

    return path


def get_base_image_path(number: int) -> Path:
    """
    Если number == 0 -> берём строго sticker512x512_00.png
    Иначе -> случайная sticker512x512_01..IMAGE_COUNT.png
    """
    images_dir = Path(__file__).parent / "images"

    if number == 0:
        path = images_dir / "sticker512x512_00.png"
        if not path.exists():
            raise FileNotFoundError(f"Zero base image not found: {path}")
        return path

    return get_random_base_image_path()


def load_font(font_paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def generate_image(number: int, output_path: str = "sticker.png") -> None:
    """
    Берём базовую картинку из папки images:
      - если number == 0 -> sticker512x512_00.png
      - иначе -> случайная sticker512x512_01..IMAGE_COUNT.png
    Рисуем число справа сверху (кроме случая number == 0)
    и три строки 'Last update', 'YYYY-MM-DD', 'HH:MM:SS' слева снизу.
    """
    base_path = get_base_image_path(number)
    img = Image.open(base_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    font_paths = [
        "font.ttf",
        "Font.ttf",
        "fonts/font.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]

    # ---------- БОЛЬШОЕ ЧИСЛО СВЕРХУ СПРАВА ----------
    # Если number == 0 — НЕ рисуем вообще ничего (ни "0", ни место под него)
    if number != 0:
        text = str(number)
        big_font = load_font(font_paths, 120)

        bbox = draw.textbbox((0, 0), text, font=big_font)
        text_w = bbox[2] - bbox[0]

        margin = 36
        x = img.width - text_w - margin - 10
        y = margin

        draw.text((x, y), text, font=big_font, fill=(0, 0, 0, 255))

    # ---------- МАЛЕНЬКИЙ ТЕКСТ В 3 СТРОКИ СНИЗУ СЛЕВА ----------
    now = datetime.now(ZoneInfo("Europe/Stockholm"))
    lines = [
        "Last update",
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
    ]

    small_font = load_font(font_paths, 22)

    line_spacing = 4
    widths = []
    heights = []
    for line in lines:
        lbbox = draw.textbbox((0, 0), line, font=small_font)
        w = lbbox[2] - lbbox[0]
        h = lbbox[3] - lbbox[1]
        widths.append(w)
        heights.append(h)

    block_h = sum(heights) + line_spacing * (len(lines) - 1)

    margin_bottom = 36
    margin_left = 36

    ux = margin_left
    uy = img.height - block_h - margin_bottom

    y_cursor = uy
    for i, line in enumerate(lines):
        draw.text((ux, y_cursor), line, font=small_font, fill=(255, 255, 255, 255))
        y_cursor += heights[i] + line_spacing

    img.save(output_path, format="PNG")


async def update_sticker() -> None:
    """
    - считает дни,
    - генерит картинку,
    - загружает её в Telegram,
    - если набора нет — создаёт,
    - если набор есть — удаляет старый стикер и добавляет новый.
    """
    token = os.environ["BOT_TOKEN"]
    set_name = os.environ["STICKER_SET_NAME"]
    set_title = os.environ["STICKER_SET_TITLE"]
    owner_user_id = int(os.environ["TELEGRAM_USER_ID"])

    number = calculate_days()
    generate_image(number)

    bot = Bot(token)

    # 1) Загружаем файл как sticker-file, получаем file_id
    with open("sticker.png", "rb") as f:
        uploaded_file = await bot.upload_sticker_file(
            user_id=owner_user_id,
            sticker=f,
            sticker_format="static",
        )

    file_id = uploaded_file.file_id

    # 2) Собираем InputSticker на основе file_id
    new_sticker = InputSticker(
        sticker=file_id,
        emoji_list=["📅"],
        format="static",
    )

    # 3) Пробуем получить набор
    try:
        sticker_set = await bot.get_sticker_set(set_name)
    except BadRequest as e:
        msg = getattr(e, "message", str(e)).lower()
        print("get_sticker_set error:", msg)
        # Набор ещё не создан — создаём новый
        if "stickerset_invalid" in msg or "stickerset not found" in msg:
            await bot.create_new_sticker_set(
                user_id=owner_user_id,
                name=set_name,
                title=set_title,
                stickers=[new_sticker],
                sticker_type="regular",
            )
            print(f"Created new sticker set {set_name} with number {number}")
            return
        else:
            raise

    # 4) Набор есть — удаляем старый стикер (если есть)
    if sticker_set.stickers:
        old_id = sticker_set.stickers[0].file_id
        try:
            await bot.delete_sticker_from_set(old_id)
            print(f"Deleted old sticker {old_id} from set {set_name}")
        except BadRequest as e:
            print("delete_sticker_from_set error:", getattr(e, "message", str(e)))

    # 5) Добавляем новый стикер в набор
    await bot.add_sticker_to_set(
        user_id=owner_user_id,
        name=set_name,
        sticker=new_sticker,
    )
    print(f"Added new sticker to set {set_name} with number {number}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(update_sticker())
