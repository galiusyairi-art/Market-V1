# מחבר Finnhub ל-Claude

שרת MCP קטן שרץ ב-Cloudflare Workers, בחינם. הוא נותן ל-Claude ולדשבורד מחירים בזמן אמת, חדשות, תאריכי דוחות ומצב שוק מ-Finnhub.

## הכלים
| כלי | מה מחזיר |
|---|---|
| `get_quotes` | מחיר עכשיו, שינוי, % שינוי, גבוה/נמוך/פתיחה, סגירה קודמת (עד 30 סימולים) |
| `get_company_news` | כותרות אחרונות למניה |
| `get_earnings_calendar` | תאריכי דוחות קרובים |
| `get_market_status` | האם השוק פתוח, ובאיזה סשן (פרה-מרקט, רגיל או אפטר-מרקט) |

## התקנה (בלי להתקין כלום על המחשב)
1. **מפתח Finnhub:** נרשמים ב-https://finnhub.io/register, ומעתיקים את ה-API key מה-Dashboard.
2. **Cloudflare:** נרשמים בחינם ב-https://dash.cloudflare.com/sign-up.
3. בתפריט: **Workers & Pages** ← **Create** ← **Start with Hello World!** ← שם: `finnhub-mcp` ← **Deploy**.
4. **Edit code** ← מוחקים את כל הקוד ← מדביקים את התוכן של `finnhub-worker.js` ← **Deploy**.
5. חוזרים ל-Worker ← **Settings** ← **Variables and Secrets** ← **Add**. מוסיפים שני משתנים מסוג **Secret**:
   - `FINNHUB_KEY`: המפתח מ-Finnhub.
   - `ACCESS_TOKEN`: מחרוזת סודית ארוכה, שמשמשת כסיסמה בכתובת.
   
   ← **Deploy**.
6. **בדיקה:** פותחים בדפדפן `https://finnhub-mcp.<החשבון-שלך>.workers.dev/mcp/<ACCESS_TOKEN>`:
   - `Method not allowed`: הכול תקין.
   - `Server not configured`: חסר אחד מהסודות.
   - `Not found`: הטוקן בכתובת לא נכון.
7. **ב-claude.ai:** Settings ← Connectors ← **Add custom connector**. שם: `Finnhub`, וכתובת: הכתובת מסעיף 6. אחר כך מפעילים אותו בשיחה, דרך תפריט המחברים.

## אבטחה
- המפתח של Finnhub שמור כסוד ב-Cloudflare, והוא לא מופיע בקוד ולא בכתובת.
- השרת עונה רק לכתובות שמכילות את ה-`ACCESS_TOKEN`. לא לשתף את הכתובת.
- המסלול החינמי של Finnhub הוא לשימוש אישי בלבד, ומוגבל לכ-60 קריאות בדקה.

## בדיקות
```bash
node test.mjs   # מריץ את השרת מול Finnhub מדומה
```
