# Telegram Sticker Countdown Updater

A small Python script that updates a Telegram sticker pack on a cron schedule. It generates a 512×512 sticker image by picking a random background, drawing a day counter since `START_DATE`, and adding a “Last update” timestamp.

If the counter would be `0`, the script uses `sticker512x512_00.png` only and does not draw the number (only the background + “Last update” text).