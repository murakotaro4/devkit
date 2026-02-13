(() => {
  const normalize = (s) => (s ? s.replace(/\s+/g, " ").trim() : "");

  const isCaptcha = () => {
    if (location.pathname.includes("validateCaptcha")) return true;
    if (document.querySelector("form[action*='validateCaptcha']")) return true;
    if (/Robot Check/i.test(document.title || "")) return true;
    return false;
  };

  const asinMatch = (location.pathname.match(/\/dp\/([A-Z0-9]{10})/i) || [])[1];
  const asin = asinMatch ? asinMatch.toUpperCase() : null;
  const canonicalUrl = asin
    ? `${location.origin}/dp/${asin}`
    : `${location.origin}${location.pathname}`;

  if (isCaptcha()) {
    return {
      asin,
      url: canonicalUrl,
      error: "captcha",
      title: normalize(document.title || "") || null,
    };
  }

  const title = normalize(document.querySelector("#productTitle")?.textContent || "");
  const priceTxt = normalize(
    document.querySelector(".a-price .a-offscreen")?.textContent || ""
  );
  const ratingTxt = normalize(
    document.querySelector("#acrPopover")?.getAttribute("title") ||
      document.querySelector("span.a-icon-alt")?.textContent ||
      ""
  );
  const reviewCountTxt = normalize(
    document.querySelector("#acrCustomerReviewText")?.textContent || ""
  );

  const bullets = [
    ...document.querySelectorAll("#feature-bullets ul li span"),
  ]
    .map((el) => normalize(el.textContent || ""))
    .filter((t) => t);

  const tech = {};
  const details = {};

  const addTableTo = (table, out) => {
    for (const row of table.querySelectorAll("tr")) {
      const th = normalize(row.querySelector("th")?.textContent || "");
      const td = normalize(row.querySelector("td")?.textContent || "");
      if (th && td) out[th] = td;
    }
  };

  for (const sel of [
    "#productDetails_techSpec_section_1",
    "#productDetails_techSpec_section_2",
  ]) {
    const table = document.querySelector(sel);
    if (table) addTableTo(table, tech);
  }

  const detailBullets = document.querySelector("#detailBullets_feature_div");
  if (detailBullets) {
    for (const li of detailBullets.querySelectorAll("li")) {
      const txt = normalize(li.textContent || "");
      const idx = txt.indexOf(":");
      if (idx <= 0) continue;
      const k = normalize(txt.slice(0, idx));
      const v = normalize(txt.slice(idx + 1));
      if (k && v) details[k] = v;
    }
  }

  const detailTable = document.querySelector("#productDetails_detailBullets_sections1");
  if (detailTable) addTableTo(detailTable, details);

  return {
    asin,
    url: canonicalUrl,
    title: title || null,
    priceTxt: priceTxt || null,
    ratingTxt: ratingTxt || null,
    reviewCountTxt: reviewCountTxt || null,
    bullets,
    tech,
    details,
  };
})();

