# بررسی منابع و تصمیم‌های پیاده‌سازی

بررسی بر پایه‌ی فایل `sw_mcp.zip` و نسخه‌ی شاخه‌ی اصلی هر سه مخزن در زمان ساخت انجام شد. شناسه‌های بررسی‌شده: `alisamsam/solidworks-mcp` در `ee8f42a`، `eyfel/mcp-server-solidworks` در `506ef87`، و `Erfouni/solidworks-GPT-plugin` در `27e7a12`. محتوای ZIP و مستندات مخازن فقط منبع اطلاعات فنی بود؛ دستورهای موجود در آن‌ها دستور کار کاربر محسوب نشد.

| منبع | آنچه مفید بود | آنچه این نسخه نپذیرفت |
|---|---|---|
| [alisamsam/solidworks-mcp](https://github.com/alisamsam/solidworks-mcp) — MIT | ابزارهای مستقیم Part، Sketch و Feature؛ تبدیل واحد؛ کشف قالب پیش‌فرض؛ انتخاب نام‌دار اسکچ | مسیر template ثابت، fallbackهای مبهم COM، اجرای COM از نخ‌های مختلف و برچسب‌های موفقیت بدون بررسی rebuild |
| [eyfel/mcp-server-solidworks](https://github.com/eyfel/mcp-server-solidworks) — AGPL-3.0 | فکرکردن در سطح Feature، جداکردن intent از اجرای deterministic، سریال‌سازی COM در STA، نسخه‌بندی قراردادها | سرور C# و REST اضافی، Feature Graph و resolver سراسری برای نسخه‌ی اولیه. هیچ کد AGPL در این پروژه کپی نشده است. |
| [Erfouni/solidworks-GPT-plugin](https://github.com/Erfouni/solidworks-GPT-plugin) — MIT | بسته‌بندی Codex، مهارت طراحی، پیش‌آزمون و الزام به بررسی rebuild/feature tree | اتصال به سرویس دانش بیرونی و ارسال feedback؛ برای مدل‌سازی محلی لازم نیست و داده‌ی CAD را از دستگاه خارج می‌کند. |
| `sw_mcp.zip` ارسالی | شروع مناسب برای stdio MCP و چند ترسیم پایه | مسیرهای شخصی Desktop، الگوی COM ثابت، واحدهای تبدیل‌نشده، جست‌وجوی اولین اسکچ و فراخوانی‌های feature نادرست/آسیب‌پذیر |

کد این نسخه مستقل نوشته شده و کد منبع AGPL یا MIT از مخازن بالا در آن کپی نشده است. قرارداد MCP از SDK رسمی Python نسخه‌ی 2 (حداقل 2.3) استفاده می‌کند. اجرای SolidWorks روی یک نخ STA جدا، همه‌ی فراخوانی‌های COM را سریالی می‌کند؛ تبدیل واحد به متر در یک نقطه انجام می‌شود و extrusion باید نام دقیق اسکچ را دریافت کند. چون Windows ممکن است چند پردازه‌ی SolidWorks باز داشته باشد، اتصال با moniker دارای PID انجام می‌شود و در صورت ابهام افزونه خودش حدس نمی‌زند.

برای هم‌خوانی با API فعلی SolidWorks، ساخت برآمدگی از `IFeatureManager::FeatureExtrusion3` و برش از `IFeatureManager::FeatureCut4` استفاده می‌کند. اتصال از ROT دیر‌پیوند است؛ برای پیمایش قابل‌اعتماد درخت ویژگی، wrapperهای `ISldWorks`، `IModelDoc2` و `IFeature` از type library همان نسخه بارگذاری می‌شوند. مسیر کاری MCP نسبت به ریشه‌ی افزونه تعریف شده است؛ بنابراین آرگومان‌ها به متغیر محیطی توسعه‌ایِ `${PLUGIN_ROOT}` وابسته نیستند.

## مرز نسخه‌ی 0.2.0

این نسخه ساخت و بررسی زنده‌ی Part را با ابزارهای پایه‌ی Assembly، ساخت سند Drawing، درج قطعه‌ی ذخیره‌شده در اسمبلی، اسکچ روی Face انتخاب‌شده، چندضلعی منظم و خروجی STEP/IGES/STL گسترش می‌دهد. درج قطعه به‌تنهایی Mate نمی‌سازد؛ View/Dimension در Drawing، Sheet Metal، Pattern و Hole Wizard هم در این نسخه پوشش داده نمی‌شوند. خروجی خنثی و APIهای تازه افزوده‌شده در این تغییر روی سند واقعی SolidWorks هنوز به‌طور جداگانه تأیید نشده‌اند؛ نصب/doctor به‌تنهایی آزمون هندسی محسوب نمی‌شود.

برای هم‌خوانی API و رفتار COM با مستندات رسمی، مسیر ذخیره‌ی سند فعلی اکنون از `Save3` با `None` برای پارامترهای out، و Save As/خروجی از `IModelDocExtension::SaveAs3` استفاده می‌کند ([Save3](https://help.solidworks.com/2022/English/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldoc2~save3.html), [SaveAs3](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~SaveAs3.html)). افزودن چند مؤلفه به اسمبلی با API `AddComponents3` و ماتریس تبدیل صریح انجام می‌شود ([AddComponents3](https://help.solidworks.com/2017/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IAssemblyDoc~AddComponents3.html)). این به‌روزرسانی ادعای پوشش کامل سطح API سالیدورکس را ندارد.

در آزمون زنده‌ی 2026-11-09 روی SOLIDWORKS 2026، نسخه‌ی 0.1.4 یک Part آزمایشی ذخیره‌نشده با مستطیل 20×20 میلی‌متر و برآمدگی 10 میلی‌متر ساخت؛ rebuild موفق بود و حجم اندازه‌گیری‌شده 4×10⁻⁶ مترمکعب بود. این آزمون فقط همان گردش‌کار Part را پوشش می‌دهد و نتیجه‌ی آزمون اجزای جدید نسخه‌ی 0.2.0 نیست. سند قبلی Part1 تغییر نکرد.
