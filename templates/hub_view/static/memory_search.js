(function () {
  var helpers = window.ADHHubView || {};
  var searchTerms = helpers.searchTerms;
  var fillTemplate = helpers.fillTemplate;

  var memoryExplorer = document.querySelector("[data-memory-explorer]");
  if (memoryExplorer) {
    var filter = memoryExplorer.querySelector("[data-memory-filter]");
    var result = memoryExplorer.querySelector("[data-memory-results]");
    var empty = memoryExplorer.querySelector("[data-memory-empty]");
    var hits = memoryExplorer.querySelector("[data-memory-hits]");
    var clear = memoryExplorer.querySelector("[data-memory-clear]");
    var firstAction = memoryExplorer.querySelector("[data-memory-first]");
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-memory-item]"));
    var showingTemplate = memoryExplorer.getAttribute("data-showing-template") || "Showing __count__ visible memory items on this page.";
    var resultTemplate = memoryExplorer.getAttribute("data-result-template") || '__count__ matches for "__query__".';
    var firstTemplate = memoryExplorer.getAttribute("data-first-template") || 'Open first match for "__query__".';
    var currentMatches = [];

    items.forEach(function (item, index) {
      if (!item.id) {
        item.id = "memory-item-" + (index + 1);
      }
    });

    function itemLabel(item) {
      var title = item.querySelector(".item-title");
      var text = (title ? title.textContent : item.textContent || "").trim();
      return text.replace(/\s+/g, " ").slice(0, 140);
    }

    function itemHaystack(item) {
      var type = item.getAttribute("data-memory-type") || "";
      return (type + " " + (item.textContent || "")).toLowerCase();
    }

    function renderHits(matches, query) {
      if (!hits) {
        return;
      }
      while (hits.firstChild) {
        hits.removeChild(hits.firstChild);
      }
      hits.hidden = !query || matches.length === 0;
      if (!query || matches.length === 0) {
        return;
      }
      matches.slice(0, 6).forEach(function (item) {
        var link = document.createElement("a");
        var strong = document.createElement("strong");
        var span = document.createElement("span");
        var type = item.getAttribute("data-memory-label") || item.getAttribute("data-memory-type") || "memory";

        link.className = "memory-filter-hit";
        link.href = "#" + item.id;
        strong.textContent = type.charAt(0).toUpperCase() + type.slice(1);
        span.textContent = itemLabel(item);
        link.appendChild(strong);
        link.appendChild(span);
        hits.appendChild(link);
      });
    }

    function openFirstMemoryMatch() {
      if (!currentMatches.length) {
        return;
      }
      var item = currentMatches[0];
      window.location.hash = item.id;
      item.scrollIntoView({ block: "start", behavior: "smooth" });
      var target = item.querySelector("a, button, [tabindex]");
      if (target && target.focus) {
        target.focus({ preventScroll: true });
      }
    }

    function updateMemoryFilter() {
      var query = (filter.value || "").trim().toLowerCase();
      var terms = searchTerms(query);
      var visible = 0;
      var matches = [];

      items.forEach(function (item) {
        var haystack = itemHaystack(item);
        var isMatch = !query || terms.some(function (term) {
          return haystack.indexOf(term) !== -1;
        });
        item.hidden = !isMatch;
        item.classList.toggle("memory-filter-match", Boolean(query && isMatch));
        if (isMatch) {
          visible += 1;
          if (query) {
            matches.push(item);
          }
        }
      });

      if (result) {
        if (query) {
          result.textContent = fillTemplate(resultTemplate, visible, filter.value.trim());
        } else {
          result.textContent = fillTemplate(showingTemplate, visible, "");
        }
      }
      currentMatches = matches;
      memoryExplorer.classList.toggle("search-active", Boolean(query));
      renderHits(matches, query);
      if (empty) {
        empty.hidden = visible !== 0;
      }
      if (clear) {
        clear.hidden = !query;
      }
      if (firstAction) {
        firstAction.hidden = !query || matches.length === 0;
        firstAction.href = matches.length ? "#" + matches[0].id : "#memory-explorer";
        firstAction.textContent = query
          ? fillTemplate(firstTemplate, matches.length, filter.value.trim())
          : "";
      }
    }

    if (filter) {
      filter.addEventListener("input", updateMemoryFilter);
      filter.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          openFirstMemoryMatch();
          filter.blur();
        }
      });
      if (firstAction) {
        firstAction.addEventListener("click", function (event) {
          event.preventDefault();
          openFirstMemoryMatch();
        });
      }
      if (clear) {
        clear.addEventListener("click", function () {
          filter.value = "";
          updateMemoryFilter();
          filter.blur();
        });
      }
      updateMemoryFilter();
    }
  }
}());
