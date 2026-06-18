// Cloudflare Worker — כפתור "נתח ריצה עכשיו".
// כפתור URL בטלגרם פותח את ה-Worker הזה (GET). ה-Worker מפעיל את workflow
// הניתוח דרך GitHub repository_dispatch, ומחזיר עמוד אישור קטן.
//
// אבטחה:
//   - ה-GitHub PAT נשמר כ-Secret של ה-Worker (GH_PAT), לעולם לא ב-URL ולא בקוד.
//   - ה-URL מוגן ב-TRIGGER_KEY (סוד משותף ב-query): רק מי שיש לו את הקישור המלא
//     (= אתה, מהצ'אט הפרטי בטלגרם) יכול להפעיל.
//
// Secrets/Vars להגדיר ב-Cloudflare (Settings → Variables):
//   GH_PAT       — fine-grained PAT, הרשאת Actions: Read & Write על ריפו Garmin-data
//   TRIGGER_KEY  — מחרוזת אקראית ארוכה שתבחר (גם ב-URL של כפתור הטלגרם)
//   GH_OWNER     — Hagay-BOT
//   GH_REPO      — Garmin-data

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = url.searchParams.get("key");

    if (!env.TRIGGER_KEY || key !== env.TRIGGER_KEY) {
      return html("⛔ גישה נדחתה", "מפתח לא תקין.", 403);
    }

    const resp = await fetch(
      `https://api.github.com/repos/${env.GH_OWNER}/${env.GH_REPO}/dispatches`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GH_PAT}`,
          "Accept": "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "garmin-coach-trigger",
        },
        body: JSON.stringify({ event_type: "run-analysis" }),
      }
    );

    if (resp.status === 204) {
      return html("✅ הניתוח רץ", "המאמן בודק את הריצה האחרונה. הניתוח יגיע לטלגרם בעוד ~30 שניות.", 200);
    }
    const detail = await resp.text();
    return html("⚠️ שגיאה", `GitHub החזיר ${resp.status}.\n${detail}`, 502);
  },
};

function html(title, body, status) {
  return new Response(
    `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;flex-direction:column;align-items:center;justify-content:center;
height:100vh;margin:0;text-align:center;padding:1rem}h1{font-size:1.6rem}p{color:#94a3b8}</style>
</head><body><h1>${title}</h1><p>${body}</p></body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } }
  );
}
