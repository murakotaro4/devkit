(() => {
  const normalize = (s) => (s ? s.replace(/\s+/g, " ").trim() : "");

  const isAsin = (s) => /^[A-Z0-9]{10}$/.test(s || "");

  const pickFirstText = (root, selectors) => {
    for (const sel of selectors) {
      const el = root.querySelector(sel);
      const t = normalize(el?.textContent || "");
      if (t) return t;
    }
    return null;
  };

  const nodes = [
    ...document.querySelectorAll(
      "div[data-component-type='s-search-result'][data-asin]"
    ),
  ];

  const items = [];
  let rank = 0;
  for (const node of nodes) {
    const asinRaw = normalize(node.getAttribute("data-asin") || "").toUpperCase();
    if (!isAsin(asinRaw)) continue;
    rank += 1;

    const title = normalize(
      node.querySelector("h2 a span")?.textContent ||
        node.querySelector("h2")?.textContent ||
        ""
    );

    let priceTxt = null;
    for (const el of node.querySelectorAll(".a-price .a-offscreen")) {
      const t = normalize(el.textContent || "");
      if (t && /[0-9]/.test(t)) {
        priceTxt = t;
        break;
      }
    }

    const ratingTxt = pickFirstText(node, ["span.a-icon-alt"]);

    const rcEl =
      node.querySelector("a[href*='customerReviews'] span") ||
      node.querySelector("a[href*='#customerReviews'] span") ||
      node.querySelector("span.s-underline-text");
    const rcTxt = normalize(rcEl?.textContent || "") || null;

    items.push({
      asin: asinRaw,
      title: title || null,
      // Tracking parameters are intentionally dropped here.
      url: `${location.origin}/dp/${asinRaw}`,
      priceTxt,
      ratingTxt,
      rcTxt,
      rank,
    });
  }

  return items;
})();

