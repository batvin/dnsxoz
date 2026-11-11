# Server Optimization & DNS Test Panel

یک پنل تحت وب سبک (Flask) که:

- سرعت شبکه سرور را بهینه می‌کند (فعال‌سازی BBR، تنظیم TCP buffers، file descriptors و ...)
- تست DNS روی چند سرور معروف (Cloudflare, Google, Quad9, OpenDNS, Shecan, Electro) انجام می‌دهد و تاخیر هرکدام را اندازه می‌گیرد
- نتایج را با نمودار و انیمیشن نمایش می‌دهد

## نصب سریع (روی سرور، با دسترسی root)

```bash
curl -fsSL https://raw.githubusercontent.com/batvin/dnsxoz/main/install.sh | sudo bash
```

بعد از نصب، پنل روی پورت `8088` بالا می‌آید:

```
http://SERVER_IP:8088
```

## نصب دستی

```bash
git clone https://github.com/batvin/dnsxoz.git
cd dnsxoz
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo python3 app.py
```

## مدیریت سرویس (بعد از نصب خودکار)

```bash
sudo systemctl status server-panel     # وضعیت
sudo systemctl restart server-panel    # ری‌استارت
journalctl -u server-panel -f          # لاگ زنده
```

## امنیت

این پنل به‌صورت پیش‌فرض بدون احراز هویت است. حتماً یکی از این کارها را انجام دهید:

- محدود کردن پورت 8088 در فایروال (`ufw allow from <YOUR_IP> to any port 8088`)
- قرار دادن پشت nginx با Basic Auth و SSL (Let's Encrypt)

## فایل‌ها

| فایل | توضیح |
|---|---|
| `app.py` | بک‌اند Flask (API بهینه‌سازی، تست DNS، اطلاعات سیستم) |
| `templates/index.html` | رابط کاربری پنل |
| `install.sh` | اسکریپت نصب خودکار (systemd service) |
| `requirements.txt` | وابستگی‌های پایتون |

## لایسنس

MIT — آزاد برای استفاده و تغییر.
