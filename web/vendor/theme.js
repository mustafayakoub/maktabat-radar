/* مِرصاد — الوضعُ الليليّ.
   طلبُ المؤلّف (2026-09-09): «يمكن للمستخدم أن يختار الوضع الليلي فيبقى عليه
   طوال التصفّح ولو بكلِّ اللغات، ويُحفَظ اختيارُه».

   يُحمَّل في <head> **بلا defer** عمدًا: الوضعُ يجب أن يُطبَّق قبل أوّل رسم،
   وإلّا ومض البياضُ في وجه القارئ لحظةً ثمّ أظلم — وهو أسوأُ من ألّا يكون.
   وسياسةُ المحتوى تمنع السكربتَ المضمَّن، فكان ملفًّا صغيرًا مستقلًّا.

   ثلاثُ حالات: "dark" · "light" · بلا اختيار (يتبع نظامَ الجهاز).
   والتخزينُ على أصل الموقع لا على الصفحة — فالاختيارُ يعبر اللغاتِ الأربع
   وكلَّ الصفحات، لأنّها كلُّها على mirsad.center. */
(function () {
  "use strict";
  var KEY = "marsadq.theme";
  var root = document.documentElement;

  function saved() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  // ⛔ عطبٌ التُقط 2026-09-10: كان «بلا اختيار» يحذف data-theme ويترك الأمرَ للـCSS،
  //    لكنّ اللوحةَ الليلية معرّفةٌ تحت [data-theme="dark"] وحدَه — فمن جهازُه ليليٌّ
  //    رأى الصفحةَ نهاريّةً والزرُّ يعرض ☀. الآن يُقرأ نظامُ الجهاز هنا ويُطبَّق
  //    **بلا حفظ**: الحفظُ للاختيار الصريح وحده، فمن لم يختر يبقى تابعًا لجهازه.
  function apply(mode) {
    if (mode !== "dark" && mode !== "light")
      mode = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    root.setAttribute("data-theme", mode);
  }

  function effective() {
    var m = saved();
    if (m === "dark" || m === "light") return m;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  apply(saved());                                  // قبل الرسم — هنا كلُّ الفائدة

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.querySelector(".thm");
    if (!btn) return;
    var icon = btn.querySelector(".thm-i");

    function paint() {
      var dark = effective() === "dark";
      if (icon) icon.textContent = dark ? "☀" : "☾";
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
      btn.setAttribute("aria-label", dark ? btn.dataset.toLight : btn.dataset.toDark);
      btn.title = btn.getAttribute("aria-label");
    }

    btn.addEventListener("click", function () {
      var next = effective() === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, next); } catch (e) { /* لا يضرّ */ }
      apply(next);
      paint();
    });

    // من لم يختر يتبع نظامَه، فإن غيّره النظامُ تغيّرت الصفحةُ معه
    try {
      matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
        if (!saved()) { apply(null); paint(); }
      });
    } catch (e) { /* متصفّحٌ قديم */ }

    paint();
  });
})();
