# Server Optimization & DNS Test Panel (v2)

یک پنل تحت وب سبک (Flask) با تم قرمز و منوی همبرگری که:

* **داشبورد منابع** — مصرف زنده CPU، رم، دیسک، لود و ترافیک شبکه
* **تست DNS** — اندازه‌گیری تاخیر روی Cloudflare، Google، Quad9، OpenDNS، Shecan، Electro و انتخاب/اعمال بهترین
* **تست میرور** — مقایسه سرعت میرورهای apt، pip و npm برای آپدیت سرور و پکیج‌ها
* **بهینه‌سازی شبکه** — فعال‌سازی BBR، تنظیم TCP buffers و sysctl

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
sudo systemctl restart server-panel    # ریاستار	
journalctl -u server-panel -f          # لاگ زنده
```

## بخش‌های پنل

| بخش | توضیح |
| --- | --- |
| داشبورد منابع | گیج CPU / رم / دیسک + لود و شبکه (به‌روزرسانی خودکار) |
| تست DNS و انتخاب | تست latency، نمایش بهترین، دکمه اعمال روی `/etc/resolv.conf` |
| تست میرور آپدیت | تست apt / pip / npm و نمایش سریع‌ترین |
| بهینه‌سازی شبکه | BBR + sysctl tweaks |
| اطلاعات سیستم | hostname، OS، uptime، DNS فعلی |

## امنیت

این پنل به‌صورت پیش‌فرض بدون احراز هویت است. حتماً یکی از این کارها را انجام دهید:

* محدود کردن پورت 8088 در فایروال:  
  `ufw allow from <YOUR_IP> to any port 8088`
* قرار دادن پشت nginx با Basic Auth و SSL (Let's Encrypt)

## فایل‌ها

| فایل | توضیح |
| --- | --- |
| `app.py` | بک‌اند Flask (API منابع، DNS، میرور، بهینه‌سازی) |
| `templates/index.html` | رابط کاربری (منوی همبرگری، تم قرمز) |
| `install.sh` | اسکریپت نصب خودکار (systemd) |
| `requirements.txt` | وابستگی‌های پایتون |

## لایسنس

MIT — آزاد برای استفاده و تغییر.
