import json
AS_OF="2026-10-09T10:40:00-04:00"
def w(name, rows):
    json.dump(rows, open(name,"w",encoding="utf-8"), ensure_ascii=False, indent=1)

w("brief.json",[
 {"key":"as_of","text":AS_OF},
 {"key":"headline","text":"החוזים מצביעים על פתיחה ירוקה אחרי יום אדום בטכנולוגיה: ריבאונד ב-AI ונפט שנרגע, אבל תשואות מעל 5% וברנט מעל 100$ עדיין מגבילים את העלייה."},
 {"key":"today","text":"אתמול הנאסד״ק ירד 1.25% וה-S&P ירד 0.5%, אחרי דיווח ב-FT שההכנסות השנתיות של OpenAI עומדות על כ-50 מיליארד$ ולא 68. זו הייתה מכה למניות תשתית ה-AI (אורקל ‎-5.5%, CoreWeave ‎-7.8%). הבוקר החוזים בירוק (נאסד״ק 100 ‎+0.8%, S&P ‏‎+0.4%) והנפט יורד אחרי שטראמפ איתת שלא יפעל מול איראן לפני הבחירות. בפרה-מרקט חמים במיוחד ביטוח הבריאות (Humana ‏‎+15% בזכות דירוגי הכוכבים), מגדלי הסלולר (SpaceX קנתה ספקטרום ב-8 מיליארד$) והאופטיקה (Lumentum מכורה עד 2029). כדאי להיזהר מתעופה (Delta ‏‎-4%) ומחברות התקשורת (T-Mobile ‏‎-7%), מדד הסנטימנט של מישיגן ירד ל-46.3, מתחת לצפי, וציפיות האינפלציה עלו ל-4.7%. בבוקר: S&P ‏‎+0.3% ונאסד״ק ‎+0.5%."},
 {"key":"week","text":"השבוע נפתח בשיאים: ה-S&P והנאסד״ק ננעלו בשיא ביום שלישי, ואחריהם הגיעו שני ימי ירידה. ה-S&P עדיין ב-‎+0.55% מתחילת השבוע, ופתיחה ירוקה היום תסגור שבוע חיובי. מה שמניע את השבוע: נפט והורמוז, תשואות האג״ח והספקות לגבי החזר ההשקעה ב-AI."},
 {"key":"social","text":"ברשתות: ב-Stocktwits הסנטימנט של הקמעונאים על SPY ו-QQQ 'בולשי מאוד', ובראש הטרנד עומדות ASTS (נפגעה מעסקת SpaceX), HUM, LITE ו-DAL. ב-WallStreetBets הבולשיות מרוכזת בשבבים ובזיכרון (MU, NVDA, ADBE), PLTR היא המניה הדובית ביותר, ו-SBUX קפצה ב-1,920% באזכורים בגלל השמועה שתציע לרכוש את Chipotle."},
 {"key":"month","text":"אוקטובר נפתח חיובי: ה-S&P עלה ב-1.5% מתחילת החודש, למרות תשואת 10 שנים שנגעה ב-5.35% (שיא מאז 2002) וברנט מעל 100$. בספטמבר הפד העלה את הריבית ל-3.75%–4%. נקודות ההכרעה של החודש הן ה-CPI ב-14.10 (הצפי 3.6%–3.7%) וה-FOMC ב-28.10. רוחב השוק חלש, והעליות מרוכזות במניות ה-AI הגדולות."}
])

w("outlook.json",[
 {"horizon":"today","label":"היום","p_up":0.63,"bias":"עלייה מתונה","drivers":"חוזים בירוק, ריבאונד AI, נפט יורד · סיכון: מישיגן 10:00, תשואות"},
 {"horizon":"week","label":"השבוע","p_up":0.70,"bias":"סגירה שבועית חיובית","drivers":"S&P ‏‎+0.55% מתחילת השבוע, צריך להחזיק מעל 7,722.72"},
 {"horizon":"month","label":"החודש","p_up":0.57,"bias":"חיובי, תנודתי","drivers":"‎+1.5% מתחילת החודש · מכשולים: CPI 14.10, ‏FOMC 28.10, בחירות 3.11"}
])

w("indices.json",[
 {"symbol":"SPX","name":"S&P 500","last_close":7765.36,"pre_pct":0.4,"day_pct":-0.47,"wtd_pct":0.55,"mtd_pct":1.49,"week_ref":7722.72,"month_ref":7651.54},
 {"symbol":"IXIC","name":"נאסד״ק","last_close":27193.34,"pre_pct":0.8,"day_pct":-1.25,"wtd_pct":0.01,"mtd_pct":1.24,"week_ref":27190.86,"month_ref":26861.06},
 {"symbol":"DJI","name":"דאו ג׳ונס","last_close":51231.64,"pre_pct":0.2,"day_pct":0.10,"wtd_pct":0.11,"mtd_pct":0.64,"week_ref":51176.96,"month_ref":50906.05}
])

def pick(rank,sym,name,prev,pre,entry,stop,tp,target,conf,thesis,cat,setup):
    cur = pre if pre is not None else prev
    return {"rank":rank,"symbol":sym,"name":name,"prev_close":prev,"pre_price":pre,
      "pre_pct": round((pre/prev-1)*100,2) if pre else None,"reg_price":None,"reg_pct":None,
      "entry":entry,"stop":stop,"take_profit":tp,"target":target,
      "target_pct":round((target/cur-1)*100,2),"confidence":conf,"thesis":thesis,"catalyst":cat,"setup":setup}
w("picks.json",[
 pick(1,"LITE","Lumentum",1048.60,1111.50,1100,1068,1130,1145,66,"המנכ״ל: הביקוש לרכיבים האופטיים עולה על ההיצע, וההזמנות מלאות עד 2029. המניה תיקנה 5.6% אתמול ומנסה לחזור לשיא ה-52 שבועות (1,137.20$).","הזמנות מלאות עד 2029","ריבאונד אחרי יום תיקון · פריצת שיא"),
 pick(2,"AMT","American Tower",166.73,178.65,177,172,183,186,64,"עסקת הספקטרום של SpaceX (800MHz) מחייבת תשתית קרקעית. מורגן סטנלי ו-JPMorgan רואים בה חיובית למגדלים.","SpaceX קנתה ספקטרום של Grain","רוטציה סקטוריאלית · REIT בתנופה"),
 pick(3,"CRWV","CoreWeave",81.58,83.62,83,79.9,87,89,61,"ירידה של 7.8% אתמול בגלל OpenAI. הבוקר מניות ה-AI מתאוששות בפרה-מרקט, והמניה עדיין ‎+14% מתחילת השנה.","ריבאונד AI אחרי מכירת יתר","מכירת יתר ליום אחד · בטא גבוהה"),
 pick(4,"MU","Micron",1035.84,None,1040,1005,1075,1090,58,"המניה הבולשית ביותר ב-WallStreetBets (217 אזכורים). ירדה 4.8% אתמול עם השבבים, והמחזור של זיכרון ה-HBM עדיין חזק.","סנטימנט קמעונאי + ריבאונד שבבים","חזרה לממוצע · אישור מעל 1,040"),
 pick(5,"CMG","Chipotle",32.65,None,32.5,31.4,33.8,34.5,55,"לפי ה-FT, סטארבקס בחנה הצעת רכש ל-Chipotle (שווי כ-39 מיליארד$). המניה עלתה 6.1% אתמול במחזור של 63.7 מיליון מניות, ו-SBUX קפצה ב-1,920% באזכורים ב-WSB.","שמועת רכישה (FT)","פרמיית מיזוג · המשך מומנטום")
])

def buzz(sym,name,prev,pre,target,stop,score,why,src,risk):
    return {"symbol":sym,"name":name,"prev_close":prev,"pre_price":pre,"pre_pct":round((pre/prev-1)*100,1),
      "reg_price":None,"target":target,"target_pct":round((target/pre-1)*100,1),"stop":stop,
      "buzz_score":score,"why":why,"sources":src,"risk":risk}
w("buzz.json",[
 buzz("HUM","Humana",387.12,447.00,465.00,432.00,92,"המניה שכולם מדברים עליה היום: בראש הטרנד ב-Stocktwits, בכל אתרי החדשות ובשרשורי Reddit. 95% מחברי ה-MA שלה בתוכניות של 4+ כוכבים, ו-Baird מסמנת יעד של 596$.","Stocktwits (טרנד) · Reddit · Reuters · Bloomberg · CNBC","בינוני · גאפ גדול עלול להיסגר"),
 buzz("VEEA","Veea",3.87,5.91,7.10,4.90,70,"‎+34%–53% בפרה-מרקט אחרי חזרה לעמידה בדרישות הנאסד״ק, עם 20 מיליון מניות בנפח. מדברים עליה בסורקים וב-Benzinga, אבל לא מצאתי אישור לבאזז ב-Reddit.","Benzinga · StockAnalysis · סורקי פרה-מרקט","קיצוני · שווי כ-12M$"),
 buzz("FRGT","Freight Technologies",0.2564,0.33,0.40,0.28,45,"מובילת העליות בפרה-מרקט (‎+28%–68%). רק בסורקים, בלי אישור ברשתות החברתיות.","Benzinga · סורקי Small-cap","קיצוני · מניית פני")
])

w("macro.json",[
 {"key":"fed","label":"ריבית הפד","value":"3.75–4.00%","note":"העלאה של 25 נ״ב ב-16.9, ראשונה מאז 2023","next":"FOMC ‏28.10 · השוק מתמחר העלאה בדצמבר","tone":"bad"},
 {"key":"y10","label":"תשואת 10 שנים","value":"5.23%","note":"נגעה ב-5.35%, שיא מאז 2002","next":"30 שנה: ~5.68%","tone":"bad"},
 {"key":"cpi","label":"אינפלציה (CPI)","value":"3.4%","note":"אוגוסט, שנתי · ליבה 2.4%","next":"ספטמבר ב-14.10 · צפי 3.6–3.7%","tone":"warn"},
 {"key":"unemp","label":"אבטלה","value":"4.2%","note":"ספטמבר, עלייה מ-4.1%","next":"דוח תעסוקה 6.11","tone":"warn"},
 {"key":"nfp","label":"משרות חדשות","value":"+29K","note":"צפי 90K · עדכון כלפי מטה של 60K","next":"שכר ‎+3.0% שנתי, הנמוך מאז 2021","tone":"bad"},
 {"key":"gdp","label":"צמיחה (תוצר)","value":"2.2%","note":"רבעון 2, אומדן שלישי (עודכן מ-1.5%)","next":"רבעון 3 ב-29.10","tone":"ok"},
 {"key":"umich","label":"סנטימנט צרכנים","value":"46.3","note":"מישיגן, אוקטובר ראשוני (צפי 47.6–48.0, קודם 48.1)","next":"ציפיות אינפלציה לשנה: 4.7% · סופי ב-23.10","tone":"bad"},
 {"key":"brent","label":"נפט ברנט","value":"$104.28","note":"‎+4% אתמול · תקיפות בהורמוז","next":"הבוקר ~102.6$ (‎-1.6%)","tone":"bad"},
 {"key":"wti","label":"נפט WTI","value":"$91.49","note":"סגירה 8.10","next":"EIA: ממוצע 105$ ברבעון 4 (ברנט)","tone":"warn"},
 {"key":"gold","label":"זהב","value":"$4,134","note":"‎+0.5% מהשפל של חודשיים","next":"","tone":"neutral"},
 {"key":"btc","label":"ביטקוין","value":"$82,167","note":"‎-1.3% אתמול","next":"","tone":"neutral"},
 {"key":"tariff","label":"מכסים / מס","value":"$820","note":"נטל המכסים למשק בית ב-2026 (Tax Foundation)","next":"מכסי IEEPA בוטלו בעליון · DC מס קנייה 6%→7%","tone":"warn"}
])

w("social.json",[
 {"symbol":"GOOG","mentions":219,"sentiment":"neutral"},
 {"symbol":"MU","mentions":217,"sentiment":"bullish"},
 {"symbol":"ADBE","mentions":199,"sentiment":"bullish"},
 {"symbol":"NVDA","mentions":152,"sentiment":"bullish"},
 {"symbol":"APLD","mentions":143,"sentiment":"bullish"},
 {"symbol":"SPCX","mentions":125,"sentiment":"neutral"},
 {"symbol":"PLTR","mentions":67,"sentiment":"bearish"}
])

w("chatter.json",[
 {"symbol":"HUM","platforms":"Stocktwits · Reddit · X","sentiment":"bullish","theme":"דירוגי כוכבים 2027, ‎+15% בפרה-מרקט"},
 {"symbol":"ASTS","platforms":"Stocktwits #1 · X · Reddit","sentiment":"bearish","theme":"SpaceX חטפה את ספקטרום Grain; B. Riley הורידה ל-Neutral"},
 {"symbol":"MU","platforms":"WSB · Reddit · Stocktwits","sentiment":"bullish","theme":"המניה הבולשית ביותר ב-WSB, ריבאונד בשבבים"},
 {"symbol":"SBUX / CMG","platforms":"WSB · X","sentiment":"neutral","theme":"שמועת רכישה של Chipotle ‏(FT), קפיצה של 1,920% באזכורים"},
 {"symbol":"SPCX","platforms":"Stocktwits · WSB · X","sentiment":"neutral","theme":"עסקת ספקטרום 8B$, נכנסת לסלולר"},
 {"symbol":"LITE","platforms":"Stocktwits · X","sentiment":"bullish","theme":"מכורה עד 2029, קרובה לשיא"},
 {"symbol":"DAL","platforms":"Stocktwits","sentiment":"bearish","theme":"פספוס בדוח, קיצוץ תחזית בגלל הדלק"},
 {"symbol":"GME","platforms":"Reddit","sentiment":"neutral","theme":"עדיין הכי מוזכרת ב-Reddit ‏(679 אזכורים)"},
 {"symbol":"PLTR","platforms":"WSB","sentiment":"bearish","theme":"המניה הדובית ביותר ב-WSB"},
 {"symbol":"RVMD · VSTM · NOK","platforms":"Stocktwits","sentiment":"neutral","theme":"בטרנד הבוקר; ל-RVMD יש ספקות של ה-FDA"},
 {"symbol":"SPY / QQQ","platforms":"Stocktwits","sentiment":"bullish","theme":"סנטימנט קמעונאי 'בולשי מאוד'"}
])

w("methods.json",[
 {"school":"ערך · באפט","method":"מרווח ביטחון, חפיר תחרותי, תמחור מול רווחים","read":"HUM נסחרת בכ-6.7× על רווחי 2028 · זול יחסית לאיכות","weight":0.15},
 {"school":"מומנטום · אוניל CAN SLIM","method":"קטליזטור חדש, מוביל סקטור, נפח מוסדי","read":"LITE ו-HUM: קטליזטור + נפח, קרובות לשיא","weight":0.20},
 {"school":"ניתוח טכני","method":"גאפים, VWAP, תמיכה/התנגדות, ממוצעים","read":"S&P מעל ממוצע 50 · שני ימי ירידה אחרי שיא = פולבק בריא","weight":0.20},
 {"school":"מאקרו · דליו","method":"ריבית, אינפלציה, נפט, דולר, מחזור","read":"פד מעלה, תשואות 5%+ ⇒ לחץ על מכפילים ועל Small-cap","weight":0.20},
 {"school":"סנטימנט וזרימות","method":"פורומים, אופציות, שווקי תחזית","read":"Polymarket: ‏94% לפתיחה גבוהה · Stocktwits: SPY/QQQ בולשי מאוד · WSB בולשי על שבבים, דובי על PLTR","weight":0.15},
 {"school":"מסחר יומי","method":"גאפ-אנד-גו, ORB, יחס סיכוי/סיכון ≥ 1:2","read":"כניסה רק אחרי 15 הדקות הראשונות · סטופ מתחת לנמוך הפתיחה","weight":0.10}
])

w("sources.json",[
 {"group":"חדשות ונתונים","name":"CNBC · Bloomberg · Reuters · Yahoo Finance","signal":"OpenAI ‏50B, עסקת SpaceX, דירוגי CMS"},
 {"group":"חדשות ונתונים","name":"Benzinga · Investing.com · TheStreet · 24/7 Wall St","signal":"מניות שזזות בפרה-מרקט, חוזים"},
 {"group":"מאקרו רשמי","name":"Federal Reserve · BLS · BEA · EIA · מישיגן","signal":"ריבית, CPI, תעסוקה, תוצר, נפט"},
 {"group":"שוק אג״ח וסחורות","name":"Schwab · BabyPips · Trading Economics","signal":"10Y ‏5.23%, ברנט 104$, זהב"},
 {"group":"רשתות ופורומים","name":"r/wallstreetbets (AltIndex, Tradestie)","signal":"MU, ADBE, NVDA בולשיות · PLTR דובית · SBUX קפצה באזכורים"},
 {"group":"רשתות ופורומים","name":"Reddit-wide (AltIndex)","signal":"GME ‏679, META ‏210 אזכורים"},
 {"group":"רשתות ופורומים","name":"Stocktwits (טרנד + חדשות)","signal":"ASTS, HUM, LITE, DAL בטרנד · SPY/QQQ בולשי מאוד"},
 {"group":"רשתות ופורומים","name":"X / FinTwit (AltIndex, Substack)","signal":"ASTS, ‏CMG, ‏GME ו-NVDA בדיון"},
 {"group":"שווקי תחזית","name":"Polymarket","signal":"94% לפתיחה גבוהה יותר"},
 {"group":"אנליסטים","name":"Baird · Evercore · Morgan Stanley · JPMorgan · Bernstein","signal":"HUM יעד 596$, מגדלים חיובי"}
])

w("calendar.json",[
 {"date":"2026-10-09","time":"10:00","event":"מישיגן: 46.3 (צפי ~47.6) · ציפיות אינפלציה 4.7%","impact":"high"},
 {"date":"2026-10-13","time":"","event":"פתיחת עונת הדוחות: בנקים","impact":"high"},
 {"date":"2026-10-14","time":"08:30","event":"מדד המחירים לצרכן CPI, ספטמבר","impact":"high"},
 {"date":"2026-10-14","time":"14:00","event":"Beige Book","impact":"med"},
 {"date":"2026-10-28","time":"14:00","event":"החלטת ריבית FOMC","impact":"high"},
 {"date":"2026-10-29","time":"08:30","event":"תוצר רבעון 3 (ראשוני)","impact":"high"},
 {"date":"2026-11-03","time":"","event":"בחירות אמצע הקדנציה","impact":"high"}
])


# ===================== decision layer =====================
w("regime.json",[
 {"key":"overall","label":"מצב השוק","status":"caution","title":"מגמת עלייה תחת לחץ","text":"ה-S&P במרחק של פחות מ-0.5% משיא כל הזמנים ומעל הממוצעים, אבל רוחב השוק חלש, התשואות מעל 5%, הנפט מעל 100$ והסנטימנט בשפל. לכן: קונים רק את המובילות עם קטליזטור, בפוזיציה מוקטנת, ולא רודפים.","day_exposure":0.75,"swing_exposure":0.5},
 {"key":"trend","label":"מגמה","status":"go","title":"S&P ליד שיא, מעל ממוצע 50 ו-200","text":"שיא סגירה ביום שלישי (6.10), שני ימי מימוש, היום ריבאונד של ‎+0.3%","day_exposure":None,"swing_exposure":None},
 {"key":"breadth","label":"רוחב שוק","status":"stop","title":"רוב המניות לא משתתפות","text":"3 מכל 4 מניות ב-S&P ירדו בספטמבר · העליות מרוכזות במגה-קאפ AI","day_exposure":None,"swing_exposure":None},
 {"key":"rates","label":"ריבית ואג״ח","status":"stop","title":"10Y ‏5.23%, הפד מעלה","text":"שיא מאז 2002 · לחץ על מכפילים ועל Small-cap","day_exposure":None,"swing_exposure":None},
 {"key":"volatility","label":"תנודתיות","status":"go","title":"VIX סביב 15, רגוע","text":"אין פאניקה · סטופים רגילים עובדים","day_exposure":None,"swing_exposure":None},
 {"key":"sentiment","label":"סנטימנט","status":"caution","title":"הקמעונאים בולשיים מאוד, הצרכנים בשפל","text":"Stocktwits: SPY/QQQ 'בולשי מאוד' (איתות נגדי) · מישיגן 46.3","day_exposure":None,"swing_exposure":None},
 {"key":"events","label":"אירועים","status":"caution","title":"CPI ביום שלישי 14.10","text":"להקטין סווינג חדש לפני ה-CPI · FOMC ב-28.10 · בחירות 3.11","day_exposure":None,"swing_exposure":None}
])

w("timing.json",[
 {"start":"04:00","end":"09:30","name":"פרה-מרקט","action":"plan","what":"בונים רשימה: גאפ, קטליזטור, נפח. מסמנים שיא/שפל פרה-מרקט וסגירה קודמת. לא נכנסים."},
 {"start":"09:30","end":"09:35","name":"5 הדקות הראשונות","action":"wait","what":"טווח הפתיחה נבנה. לא נכנסים, רק מסתכלים מי מחזיקה מעל VWAP."},
 {"start":"09:35","end":"10:30","name":"חלון הזהב","action":"go","what":"פריצות טווח פתיחה וגאפ-אנד-גו במניות במשחק. גודל פוזיציה מלא ל-A."},
 {"start":"10:30","end":"11:30","name":"הזדמנות שנייה","action":"go","what":"פולבק ראשון ל-VWAP או לממוצע 9 בגרף 5 דק׳ במניות שהובילו."},
 {"start":"11:30","end":"14:00","name":"שעות הצהריים","action":"wait","what":"נפח נמוך ותנודות שווא. חצי פוזיציה או בכלל לא. מנהלים את מה שפתוח."},
 {"start":"14:00","end":"15:00","name":"חזרת המגמה","action":"go","what":"פריצות של טווח הצהריים בכיוון המגמה היומית."},
 {"start":"15:00","end":"15:50","name":"שעת הכוח","action":"go","what":"המשך מגמה. סוגרים עסקאות יומיות. מחליטים על כניסות סווינג לפי חוזק הסגירה."},
 {"start":"15:50","end":"16:00","name":"סגירה","action":"plan","what":"כניסת סווינג רק אם המניה נסגרת בחצי העליון של הטווח היומי."}
])

def day(sym,name,prev,pm,trig,stop,t1,t2,grade,catalyst,checks,plan,avoid,side=1):
    risk=abs(trig-stop)
    return {"symbol":sym,"name":name,"side":side,"prev_close":prev,"pm_price":pm,"gap_pct":round((pm/prev-1)*100,1),
      "trigger":trig,"stop":stop,"t1":t1,"t2":t2,"r_t1":round(abs(t1-trig)/risk,1),"r_t2":round(abs(t2-trig)/risk,1),
      "grade":grade,"catalyst":catalyst,"checks":checks,"plan":plan,"avoid":avoid}
w("daytrade.json",[
 day("HUM","Humana",387.12,447.00,450.00,438.00,462.00,472.00,"A","דירוגי כוכבים 2027 (CMS): 95% מהחברים ב-4+ כוכבים",
     "קטליזטור:1|נפח חריג:1|גאפ 4%+:1|נזילות גבוהה:1|סקטור תומך:0|מעל VWAP:1",
     "ORB: כניסה מעל שיא 5 הדקות הראשונות / מעל 450, רק כשהמחיר מעל VWAP. מימוש חלקי ב-462.","מתחת ל-VWAP אחרי 10:00 · גאפ של 15% עלול להיסגר חלקית"),
 day("LITE","Lumentum",1048.60,1111.50,1115.00,1095.00,1137.20,1160.00,"A","המנכ״ל: ההזמנות מלאות עד 2029",
     "קטליזטור:1|נפח חריג:1|גאפ 4%+:1|נזילות גבוהה:1|סקטור תומך:1|מעל VWAP:1",
     "פריצה מעל 1,115 עם החזקה מעל VWAP. יעד ראשון בשיא 52 השבועות (1,137.20).","כישלון ב-1,137 (התנגדות כפולה) · שבבים חוזרים לרדת"),
 day("AMT","American Tower",166.73,178.65,179.50,175.80,183.00,186.00,"B","SpaceX קנתה ספקטרום ב-8B$ · נדרשת תשתית קרקעית",
     "קטליזטור:1|נפח חריג:1|גאפ 4%+:1|נזילות גבוהה:1|סקטור תומך:1|מעל VWAP:0",
     "רק פולבק ל-VWAP שמחזיק (10:30–11:30). REIT איטי, המטרות צנועות.","המניה במגמת ירידה ארוכה: לא להחזיק ללילה"),
 day("CRWV","CoreWeave",81.58,83.62,84.20,82.40,86.50,89.00,"B","ריבאונד AI אחרי ‎-7.8% אתמול",
     "קטליזטור:0|נפח חריג:1|גאפ 4%+:0|נזילות גבוהה:1|סקטור תומך:1|מעל VWAP:1",
     "פריצה מעל שיא הפתיחה כשהנאסד״ק ירוק. סטופ צמוד: מניה עם בטא גבוהה.","אם הנאסד״ק מאבד את הירוק · אין קטליזטור משלה"),
 day("VEEA","Veea",3.87,5.91,6.10,5.50,6.80,7.40,"C","חזרה לעמידה בדרישות הנאסד״ק",
     "קטליזטור:1|נפח חריג:1|גאפ 4%+:1|נזילות גבוהה:0|סקטור תומך:0|מעל VWAP:1",
     "ספקולציה: רבע פוזיציה בלבד, רק פריצה של שיא הפרה-מרקט עם נפח. לצאת מהר.","שווי 12M$ · מרווחים רחבים · הצפת מניות אפשרית")
])

def sw(sym,name,last,pivot,stop,target,status,trend,earn,verdict,reason,action):
    return {"symbol":sym,"name":name,"last":last,"pivot":pivot,"zone_top":round(pivot*1.05,2),"stop":stop,"target":target,
      "dist_pivot_pct":round((last/pivot-1)*100,1),"risk_pct":round((stop/pivot-1)*100,1),"target_pct":round((target/pivot-1)*100,1),
      "status":status,"trend":trend,"earnings":earn,"verdict":verdict,"reason":reason,"action":action}
w("swing_setups.json",[
 sw("LITE","Lumentum",1048.60,1137.20,1057.60,1364.60,"בבסיס, 7.8% מתחת לנקודת הקנייה","5/5: מעל ממוצע 50/150/200, ‎+171% מתחילת השנה, קרובה לשיא","תחילת נובמבר (לא מאומת)",
    "watch","מובילה בסקטור חזק עם קטליזטור של שנים. קונים רק בפריצה מעל 1,137.20 בנפח גבוה ב-40% מהממוצע, ועד 5% מעל.","wait"),
 sw("MU","Micron",1035.84,1088.50,1012.30,1306.20,"פולבק של 4.8% מהשיא","5/5: מגמה חזקה אחרי דוח מצוין בספטמבר","דצמבר: אין סיכון דוח קרוב",
    "watch","המניה הבולשית ביותר ב-WSB. קונים בחזרה מעל 1,088.50, או בהחזקה של ממוצע 21 יום בנפח יורד.","wait"),
 sw("HUM","Humana",447.00,447.00,425.00,520.00,"גאפ של 15% מעל 387.12 (מחיר פרה-מרקט)","2/5: המניה הייתה בירידה ארוכה, הגאפ מתחיל תיקון מגמה","סוף אוקטובר: מקטינים לפני",
    "conditional","גאפ על קטליזטור יסודי (בונוסים של מיליארדים). כניסה רק אם היום נסגר בחצי העליון של הטווח; סטופ מתחת לשפל של היום.","buy_close"),
 sw("AMT","American Tower",178.65,178.65,170.00,190.00,"קפיצה של 7% מאזור השפל השנתי (מחיר פרה-מרקט)","0/5: מתחת לממוצעים, במגמת ירידה","27.10: דוח בעוד 18 יום",
    "avoid","קפיצה על כותרת במניה במגמת ירידה, עם דוח קרוב. זה טרייד יומי, לא סווינג.","avoid"),
 sw("CMG","Chipotle",32.65,32.65,30.40,36.00,"‎+6.1% על שמועת רכישה","1/5: עדיין מתחת לממוצע 200","סוף אוקטובר",
    "avoid","שמועת מיזוג שלא אושרה (Starbucks הכחישה). אם השמועה מתפוגגת, המניה חוזרת לנקודת המוצא.","avoid")
])

w("sectors.json",[
 {"sector":"אנרגיה","etf":"XLE","week_pct":1.06,"ytd_pct":48.81,"view":"lead"},
 {"sector":"טכנולוגיה","etf":"XLK","week_pct":None,"ytd_pct":37.86,"view":"lead"},
 {"sector":"תשתיות","etf":"XLU","week_pct":0.43,"ytd_pct":None,"view":"neutral"},
 {"sector":"צריכה מחזורית","etf":"XLY","week_pct":-0.47,"ytd_pct":None,"view":"neutral"},
 {"sector":"חומרי גלם","etf":"XLB","week_pct":-2.53,"ytd_pct":None,"view":"lag"},
 {"sector":"בריאות","etf":"XLV","week_pct":-2.65,"ytd_pct":9.97,"view":"lag"}
])
