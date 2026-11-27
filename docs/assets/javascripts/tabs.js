/* A link to a heading inside a content tab opens that tab first, so the table of
 * contents works for both languages on the API page. */
(function () {
  "use strict";
  function reveal() {
    var id = decodeURIComponent(window.location.hash.slice(1));
    var target = id && document.getElementById(id);
    var block = target && target.closest(".tabbed-block");
    if (!block) return;
    var set = block.closest(".tabbed-set");
    var index = Array.prototype.indexOf.call(block.parentElement.children, block);
    var input = set.querySelectorAll(":scope > input")[index];
    if (input && !input.checked) input.click();
    target.scrollIntoView();
  }
  window.addEventListener("hashchange", reveal);
  window.addEventListener("load", reveal);
})();
