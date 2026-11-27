/* Render the maths that pymdownx.arithmatex marks, with the vendored KaTeX. */
(function () {
  "use strict";
  function render() {
    document.querySelectorAll(".arithmatex").forEach(function (node) {
      window.renderMathInElement(node, {
        delimiters: [
          { left: "\\(", right: "\\)", display: false },
          { left: "\\[", right: "\\]", display: true }
        ],
        throwOnError: false,
        /* \cost{...} colours the terms that lower a score */
        macros: { "\\cost": "\\htmlClass{cost}{#1}" },
        trust: function (context) { return context.command === "\\htmlClass"; },
        strict: function (code) { return code === "htmlExtension" ? "ignore" : "warn"; }
      });
    });
  }
  /* A deferred script runs once the document is parsed: render at once. */
  if (document.querySelector(".arithmatex")) render();
  else document.addEventListener("DOMContentLoaded", render);
})();
