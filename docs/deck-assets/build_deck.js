const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.SKILL + "/scripts/apply_theme.js");

const THEME = {
  name: "Sargas",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "141922", lt1: "FFFFFF", dk2: "232B3A", lt2: "EEF1F6",
    accent1: "E5534B", accent2: "E9A23B", accent3: "2E9E62", accent4: "3D6FD8",
    accent5: "7A8394", accent6: "1B2230", hlink: "3D6FD8", folHlink: "7A8394",
  },
};
const HEX = THEME.colors;

async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.title = "Sargas";
  pres.author = "Team Sargas";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------- layouts ----------
  pres.defineSlideMaster({
    title: "Dark title",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.3, w: 11.7, h: 1.4, fontSize: 60, bold: true, color: C.background1, valign: "bottom", align: "left" }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.8, w: 11.7, h: 1.2, fontSize: 24, color: C.background2, valign: "top", align: "left" }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "Light content",
    background: { color: C.background1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.45, w: 12.1, h: 0.8, fontSize: 30, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "Sargas · Junction 2026 · botswarm.tech", options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.accent5 } } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.accent5, align: "right" },
  });
  pres.defineSlideMaster({
    title: "Dark content",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.45, w: 12.1, h: 0.8, fontSize: 30, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.accent5, align: "right" },
  });

  const ic = {
    robot: await icon(fa.FaRobot, HEX.lt1), link: await icon(fa.FaLink, HEX.lt1), clock: await icon(fa.FaClock, HEX.lt1),
    gavel: await icon(fa.FaGavel, HEX.lt1), horse: await icon(fa.FaHorse, HEX.lt1), chart: await icon(fa.FaChartBar, HEX.lt1),
    bolt: await icon(fa.FaBolt, HEX.lt1), mobile: await icon(fa.FaMobileAlt, HEX.lt1), shield: await icon(fa.FaShieldAlt, HEX.lt1),
    user: await icon(fa.FaUserCheck, HEX.lt1), brain: await icon(fa.FaBrain, HEX.lt1), eye: await icon(fa.FaEye, HEX.lt1),
  };
  const dot = (s, x, y, d, fill, img, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: name + " circle" });
    s.addImage({ data: img, x: x + d * 0.25, y: y + d * 0.25, w: d * 0.5, h: d * 0.5, objectName: name + " icon", altText: name });
  };
  const T = (s, text, o) => s.addText(text, { isTextBox: true, margin: 0, valign: "top", ...o });
  const bars = (s, { x, y, w, h, title, rows, max, labelW, fmt }) => {
    T(s, title, { x, y, w, h: 0.35, fontSize: 14, color: C.text2 });
    const top = y + 0.5, rh = (h - 0.5) / rows.length, bw = w - labelW - 0.8;
    rows.forEach(([label, v, col], k) => {
      const yy = top + k * rh;
      T(s, label, { x, y: yy, w: labelW - 0.15, h: rh, fontSize: 13, color: C.text1, valign: "middle", align: "right" });
      const len = Math.max(0.04, bw * v / max);
      s.addShape(pres.shapes.RECTANGLE, { x: x + labelW, y: yy + rh * 0.2, w: len, h: rh * 0.6, fill: { color: col }, line: { type: "none" }, objectName: label + " bar" });
      T(s, fmt(v), { x: x + labelW + len + 0.1, y: yy, w: 0.8, h: rh, fontSize: 13, bold: true, color: C.text1, valign: "middle" });
    });
  };

  // ---------- 1. Title ----------
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "Dark title", sectionTitle: "Opening" });
  s.addText("Sargas", { placeholder: "title" });
  s.addText("Finding the bot-nets behind propaganda and free-tier abuse", { placeholder: "body" });
  s.addImage({ path: process.env.SHOTS + "/swarm.gif", x: 9.55, y: 0.35, w: 3.2, h: 1.8, objectName: "swarm animation", altText: "Animated swarm of accounts drifting together and linking up" });
  T(s, "Hostinger challenge: Decode the Noise", { x: 0.8, y: 5.4, w: 9, h: 0.4, fontSize: 16, color: C.accent5 });
  T(s, "Live: botswarm.tech · guard.botswarm.tech · attack.botswarm.tech", { x: 0.8, y: 5.9, w: 9, h: 0.4, fontSize: 16, color: C.background1, bold: true });
  s.addNotes("Propaganda online doesn't need many people. It needs many accounts. Bot-nets turn a handful of operators into what looks like a crowd. We built Sargas to find those swarms of fake accounts, and to explain every verdict.");

  // ---------- 2. Propaganda ----------
  pres.addSection({ title: "Problem" });
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "Problem" });
  s.addText("Propaganda runs on fake accounts", { placeholder: "title" });
  const props = [
    [ic.robot, "Astroturfing", "A few operators run thousands of accounts so one message looks like a crowd's opinion", C.accent1],
    [ic.bolt, "Brigading", "Coordinated accounts pile onto a post, a review page or a vote at the same moment", C.accent2],
    [ic.chart, "Bot-nets", "Networks of automated accounts like, follow and review on cue so a message looks trusted", C.accent4],
  ];
  props.forEach(([img, head, body, col], k) => {
    const x = 0.6 + k * 4.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.6, w: 3.8, h: 3.5, rectRadius: 0.15, fill: { color: C.background2 }, line: { type: "none" }, objectName: head + " card" });
    dot(s, x + 0.35, 1.9, 0.9, col, img, head);
    T(s, head, { x: x + 0.35, y: 3.0, w: 3.1, h: 0.5, fontSize: 22, bold: true, color: C.text1, fontFace: THEME.headFontFace });
    T(s, body, { x: x + 0.35, y: 3.55, w: 3.1, h: 1.4, fontSize: 16, color: C.text2 });
  });
  T(s, "Every one of these starts the same way: someone opens a lot of accounts.", { x: 0.6, y: 5.55, w: 12.1, h: 0.6, fontSize: 22, italic: true, color: C.text2 });
  s.addNotes("The brief talks about bot networks shaping opinion. Astroturfing, brigading and bot-nets all need the same raw material: large numbers of accounts that look real one by one. Stop the accounts, and the propaganda has nothing to speak through.");

  // ---------- 3. Free tiers ----------
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "Problem" });
  s.addText("Free tiers are where those accounts come from", { placeholder: "title" });
  const pains = [
    ["Spam and phishing", "Fake accounts host scams and send spam under the site's name, and the owner answers for it", C.accent1],
    ["Burned resources", "Free compute, storage and support time go to accounts that will never be customers", C.accent2],
    ["Hard to see", "Each account looks real alone, and farms rotate home IP addresses, so per-request blocking misses them", C.accent4],
  ];
  pains.forEach(([head, body, col], k) => {
    const y = 1.6 + k * 1.55;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 7.4, h: 1.35, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: head + " row" });
    s.addShape(pres.shapes.OVAL, { x: 0.9, y: y + 0.47, w: 0.4, h: 0.4, fill: { color: col }, line: { type: "none" }, objectName: head + " marker" });
    T(s, head, { x: 1.55, y: y + 0.18, w: 6.2, h: 0.45, fontSize: 20, bold: true, color: C.text1, fontFace: THEME.headFontFace });
    T(s, body, { x: 1.55, y: y + 0.62, w: 6.2, h: 0.65, fontSize: 15, color: C.text2 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.4, y: 1.6, w: 4.3, h: 4.45, rectRadius: 0.15, fill: { color: C.text1 }, line: { type: "none" }, objectName: "site owner callout" });
  T(s, "For anyone who runs a free tier, this is a daily problem: every signup form is a door, and bot-nets knock in crowds.", { x: 8.8, y: 2.0, w: 3.5, h: 3.6, fontSize: 22, bold: true, color: C.background1, fontFace: THEME.headFontFace });
  s.addNotes("Where do propaganda accounts come from? Free tiers: signup forms on websites, apps and platforms. Site owners pay twice: their free resources get burned, and scams and spam run under their name. And per-request blocking misses it, because each account looks normal and farms rotate residential IPs.");

  // ---------- 4. Idea / pipeline ----------
  pres.addSection({ title: "Solution" });
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "Solution" });
  s.addText("Sargas spots the swarm, not the single account", { placeholder: "title" });
  const steps = [
    [ic.user, "Check each signup", "Inbox tricks, hidden field, form speed, mouse and typing rhythm, latency", C.accent4],
    [ic.link, "Link the swarm", "Signups that share rare details: device, inbox, email template, browser build", C.accent2],
    [ic.clock, "Test the timing", "Against 4,000 random groups: does the burst beat chance?", C.accent5],
    [ic.gavel, "Decide and explain", "Block, review or allow, with every reason shown", C.accent1],
  ];
  steps.forEach(([img, head, body, col], k) => {
    const x = 0.6 + k * 3.1;
    dot(s, x + 0.95, 1.75, 1.0, col, img, head);
    if (k < 3) s.addShape(pres.shapes.LINE, { x: x + 2.15, y: 2.25, w: 1.7, h: 0, line: { color: HEX.accent5, width: 2, endArrowType: "triangle" }, objectName: "arrow " + k });
    T(s, head, { x, y: 3.0, w: 2.9, h: 0.5, fontSize: 20, bold: true, color: C.text1, align: "center", fontFace: THEME.headFontFace });
    T(s, body, { x: x + 0.1, y: 3.55, w: 2.7, h: 1.5, fontSize: 15, color: C.text2, align: "center" });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 5.35, w: 12.1, h: 1.1, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: "caught later callout" });
  T(s, [{ text: "Caught after signup: ", options: { bold: true, color: C.accent1 } },
        { text: "accounts that got in early are blocked the moment their swarm forms.", options: { color: C.text1 } }],
    { x: 0.9, y: 5.55, w: 11.5, h: 0.7, fontSize: 20, valign: "middle" });
  s.addNotes("Sargas judges groups of accounts. It checks each signup, links signups that share rare details, tests whether the group's timing beats chance, then decides with reasons. Because it re-judges on every signup, accounts that slipped in are caught once the swarm forms.");

  // ---------- 5. Live: the site ----------
  pres.addSection({ title: "Live demo" });
  s = pres.addSlide({ masterName: "Dark content", sectionTitle: "Live demo" });
  s.addText("Live on Hostinger: try to get past it", { placeholder: "title" });
  s.addImage({ path: process.env.SHOTS + "/neighbr_c.png", x: 0.6, y: 1.55, w: 7.4, h: 4.625, objectName: "Neighbr screenshot", altText: "Screenshot of the Neighbr signup page, the satirical free tier Sargas protects" });
  s.addImage({ path: process.env.SHOTS + "/live.gif", x: 8.45, y: 1.55, w: 0.55, h: 0.55, objectName: "live pulse", altText: "Pulsing live indicator" });
  T(s, "Running now", { x: 9.1, y: 1.6, w: 3.6, h: 0.45, fontSize: 18, bold: true, color: C.accent3, valign: "middle" });
  const pages = [["botswarm.tech", "Neighbr, a satirical \"Tinder for horses\" with a free tier. Sign up and watch your own bot score live."],
                 ["guard.botswarm.tech", "The Sargas dashboard: scores, swarms, review queue, IP bans."],
                 ["attack.botswarm.tech", "Launch real bot campaigns and watch them get caught."]];
  pages.forEach(([url, body], k) => {
    const y = 2.4 + k * 1.35;
    T(s, url, { x: 8.45, y, w: 4.3, h: 0.4, fontSize: 18, bold: true, color: C.background1, fontFace: THEME.headFontFace });
    T(s, body, { x: 8.45, y: y + 0.42, w: 4.3, h: 0.85, fontSize: 14, color: C.background2 });
  });
  T(s, "Screenshot of the live site, 15 November 2026", { x: 0.6, y: 6.3, w: 7.4, h: 0.3, fontSize: 11, color: C.accent5 });
  s.addNotes("Everything is live on our Hostinger VPS. Scan the QR code on the dashboard and sign up your horse on Neighbr. You'll get a ticket and a live bot score, around 1 out of 100 for a real person.");

  // ---------- 6. Live: the dashboard ----------
  s = pres.addSlide({ masterName: "Dark content", sectionTitle: "Live demo" });
  s.addText("Every verdict explained, live", { placeholder: "title" });
  s.addImage({ path: process.env.SHOTS + "/dash_swarm.png", x: 1.12, y: 1.5, w: 6.19, h: 5.19, objectName: "dashboard swarm screenshot", altText: "Dashboard: a 15-account swarm from 3 devices, blocked, with an AI summary and the IP ban list" });
  s.addImage({ path: process.env.SHOTS + "/dash_people.png", x: 7.61, y: 1.5, w: 4.58, h: 5.19, objectName: "dashboard people screenshot", altText: "Dashboard: each person's live bot score with every factor and the AI's second opinion" });
  T(s, "From a real run: 17 bot accounts launched, 17 blocked (3 of them after signup), 2 real people allowed", { x: 0.6, y: 6.8, w: 12.1, h: 0.3, fontSize: 12, color: C.accent5 });
  s.addNotes("This is the dashboard during a real run. Left: the stealth farm, 15 accounts from 3 devices with one email template, blocked, with an AI summary in plain words and the IP ban list. Right: every person's live score, each factor with its value and weight, and the AI's second opinion.");

  // ---------- 5. The equation ----------
  pres.addSection({ title: "How it decides" });
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "How it decides" });
  s.addText("One published equation, 18 factors, every point explained", { placeholder: "title" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 1.55, w: 12.1, h: 0.95, rectRadius: 0.12, fill: { color: C.text1 }, line: { type: "none" }, objectName: "equation band" });
  T(s, "score = 100 / (1 + e^-z),   z = -4 + Σ weight × factor", { x: 0.9, y: 1.62, w: 11.5, h: 0.8, fontSize: 24, bold: true, color: C.background1, valign: "middle", fontFace: "Courier New" });
  const groupsF = [
    ["Signup", ["Throwaway inbox +3.0", "Same inbox, other spelling +3.5", "Automation browser +4.0", "Hidden field filled +5.0", "Device reused +3.0"], C.accent4],
    ["Behaviour", ["No mouse, touch or typing +1.5", "Robotic movement +2.0", "Natural movement −1.5", "Latency too low +0.5"], C.accent2],
    ["AI on the server", ["d1: email looks machine-made +1.0", "Benchmarked: AUC 0.80"], C.accent5],
    ["Group", ["Size of linked group +1.5", "Matches shared details +2.0", "Timing beats chance +2.5", "School or company −3.0"], C.accent1],
  ];
  groupsF.forEach(([head, items, col], k) => {
    const x = 0.6 + k * 3.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 2.8, w: 2.9, h: 3.4, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: head + " card" });
    s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: 3.02, w: 0.3, h: 0.3, fill: { color: col }, line: { type: "none" }, objectName: head + " marker" });
    T(s, head, { x: x + 0.65, y: 2.97, w: 2.1, h: 0.4, fontSize: 18, bold: true, color: C.text1, fontFace: THEME.headFontFace });
    s.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
      { x: x + 0.2, y: 3.5, w: 2.6, h: 2.6, fontSize: 14, color: C.text2, paraSpaceAfter: 6, valign: "top", isTextBox: true, margin: 0 });
  });
  T(s, "0–34 allow · 35–59 review · 60+ block. Weights are set by hand and published: a ranking score, not a probability.", { x: 0.6, y: 6.4, w: 12.1, h: 0.4, fontSize: 14, color: C.text2 });
  s.addNotes("No black box. Every score is one equation with 18 factors, each between 0 and 1, times a published weight. Natural human movement and schools or companies lower the score. Every point shows its reason in plain words on the dashboard and on your phone.");

  // ---------- 6. Results chart ----------
  pres.addSection({ title: "Results" });
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "Results" });
  s.addText("Every farm caught, every innocent look-alike let through", { placeholder: "title" });
  {
    const names = ["Throwaway-inbox script", "Gmail alias farm", "Residential proxy farm", "Nightly server batch", "Human-like bot (miss)",
                   "School class", "Company team", "Families on one laptop", "VPN users", "Newsletter rush"];
    const vals = [100, 100, 100, 100, 0, 0, 0, 0, 0, 0];
    const cols = [C.accent1, C.accent1, C.accent1, C.accent1, C.accent5, C.accent3, C.accent3, C.accent3, C.accent3, C.accent3];
    bars(s, { x: 0.6, y: 1.5, w: 7.6, h: 5.2, title: "Share blocked per group, 5 forged signup logs", rows: names.map((n, k) => [n, vals[k], cols[k]]), max: 100, labelW: 2.9, fmt: v => v + "%" });
  }
  const stats = [["0", "of 16,864 real people blocked", C.accent3], ["85.7%", "of bots blocked (also on attackers we never tuned for)", C.accent1], ["0.93", "AUC: how well the score separates bots from people", C.accent4]];
  stats.forEach(([big, small, col], k) => {
    T(s, big, { x: 8.6, y: 1.7 + k * 1.7, w: 4.1, h: 0.9, fontSize: 54, bold: true, color: col, fontFace: THEME.headFontFace });
    T(s, small, { x: 8.6, y: 2.6 + k * 1.7, w: 4.1, h: 0.7, fontSize: 15, color: C.text2 });
  });
  s.addNotes("Measured on ten forged signup logs with an answer key, including smarter attackers we never tuned for, and innocent traps: a school class on one IP, a company team, families on one laptop, VPN users, a newsletter rush. Zero of 16,864 real people blocked; 85.7 percent of bots blocked. Our honest miss is the human-like bot.");

  // ---------- 7. AI where it helps ----------
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "Results" });
  s.addText("AI only where it measurably beat the algorithm", { placeholder: "title" });
  bars(s, { x: 0.6, y: 1.5, w: 5.6, h: 3.4, title: "Real people flagged on 120 labelled signups", max: 20, labelW: 2.4, fmt: v => String(v),
    rows: [["Algorithm", 0, C.accent3], ["d1-omni-600M as judge", 17, C.accent1], ["LFM3-VL-2B as judge", 10, C.accent1]] });
  T(s, "Both on-server models lost as judges. Hand-picked examples made the LLM look perfect; the labelled benchmark didn't.",
    { x: 0.6, y: 5.1, w: 5.6, h: 1.2, fontSize: 16, italic: true, color: C.text2 });
  const jobs = [
    [ic.gavel, "Block / review / allow", "Algorithm: AUC 0.90, 0 people flagged", C.accent3],
    [ic.brain, "Email looks machine-made", "d1 factor: AUC 0.80 (name prompts near chance, dropped)", C.accent4],
    [ic.chart, "Ranking the review queue", "Algorithm + d1 blend: AUC 0.90 → 0.94", C.accent2],
    [ic.robot, "Summaries in plain words", "LFM3-VL-2B writes each swarm's summary; never changes a verdict", C.accent5],
  ];
  jobs.forEach(([img, head, body, col], k) => {
    const y = 1.6 + k * 1.25;
    dot(s, 6.8, y, 0.8, col, img, head);
    T(s, head, { x: 7.8, y: y - 0.02, w: 4.9, h: 0.4, fontSize: 18, bold: true, color: C.text1, fontFace: THEME.headFontFace });
    T(s, body, { x: 7.8, y: y + 0.4, w: 4.9, h: 0.6, fontSize: 15, color: C.text2 });
  });
  s.addNotes("We ran Liquid AI's d1 and LFM3 on the VPS with llama.cpp and benchmarked them on labelled data, including a Hugging Face dataset of real Twitter bots. As judges they flagged 17 and 10 real people; the algorithm flagged none. So the algorithm decides, and AI does what it measured better at: reading email patterns, ranking the review queue, and writing plain-language summaries.");

  // ---------- 8. False positives and limits ----------
  pres.addSection({ title: "Honesty" });
  s = pres.addSlide({ masterName: "Light content", sectionTitle: "Honesty" });
  s.addText("Built against false positives, open about what it misses", { placeholder: "title" });
  const cols = [
    ["How we protect real people", C.accent3, ["Weak signals (VPN, digits in a name) can never block alone", "Natural movement and school/company groups lower the score", "A review band instead of a hard block for uncertain cases", "IP bans need 2 blocked accounts; each has an off switch and reset", "Two identical phones still count as two devices"]],
    ["What we don't catch yet", C.accent1, ["A careful bot that replays human input and varies every detail", "Accuracy so far is measured on forged logs written by us", "No IP-to-location check yet (timezone mismatch is collected, not scored)", "Emails and IPs are stored unhashed until the demo is reset"]],
  ];
  cols.forEach(([head, col, items], k) => {
    const x = 0.6 + k * 6.15;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.6, w: 5.95, h: 4.9, rectRadius: 0.15, fill: { color: C.background2 }, line: { type: "none" }, objectName: head + " card" });
    dot(s, x + 0.35, 1.9, 0.7, col, k ? ic.eye : ic.shield, head);
    T(s, head, { x: x + 1.25, y: 2.0, w: 4.5, h: 0.5, fontSize: 20, bold: true, color: C.text1, fontFace: THEME.headFontFace });
    s.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })),
      { x: x + 0.35, y: 2.85, w: 5.3, h: 3.5, fontSize: 16, color: C.text2, paraSpaceAfter: 8, valign: "top", isTextBox: true, margin: 0 });
  });
  s.addNotes("False positives were designed against from the start. And we show our misses on the dashboard itself: the human-like bot gets in, and our numbers come from forged logs, so real labelled data is the next step.");

  // ---------- Close ----------
  pres.addSection({ title: "Close" });
  s = pres.addSlide({ masterName: "Dark title", sectionTitle: "Close" });
  s.addText("Find the swarm before it speaks", { placeholder: "title", fontSize: 48 });
  s.addText("Sargas: bot-net detection for propaganda and free-tier abuse. Live on Hostinger now: demo.botswarm.tech", { placeholder: "body" });
  s.addImage({ path: process.env.SHOTS + "/swarm.gif", x: 9.55, y: 5.0, w: 3.2, h: 1.8, objectName: "swarm animation", altText: "Animated swarm of accounts drifting together and linking up" });
  T(s, "Team Sargas · Demo: demo.botswarm.tech · github.com/cnordenb/Junction2026_Sargas", { x: 0.8, y: 5.9, w: 8.8, h: 0.4, fontSize: 16, color: C.accent5 });
  s.addNotes("Propaganda needs a crowd, and bot-nets fake one through free tiers. Sargas finds the swarm before it speaks, explains every verdict, and shows its own error rate. It's live on Hostinger right now: scan, sign up and try to get past it.");

  const out = process.env.OUT;
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out);
})();
