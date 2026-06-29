(function () {
  var helpers = window.ADHHubView || {};
  var searchTerms = helpers.searchTerms;
  var fillTemplate = helpers.fillTemplate;

  var inboxFilter = document.querySelector("[data-inbox-filter]");
  if (inboxFilter) {
    var inboxInput = inboxFilter.querySelector("[data-inbox-filter-input]");
    var inboxResult = inboxFilter.querySelector("[data-inbox-filter-result]");
    var inboxEmpty = inboxFilter.querySelector("[data-inbox-empty]");
    var inboxClear = inboxFilter.querySelector("[data-inbox-clear]");
    var inboxItems = Array.prototype.slice.call(document.querySelectorAll("[data-inbox-item]"));
    var inboxGroups = Array.prototype.slice.call(document.querySelectorAll("[data-inbox-group]"));
    var inboxShowingTemplate = inboxFilter.getAttribute("data-showing-template") || "Visible review items: __count__.";
    var inboxResultTemplate = inboxFilter.getAttribute("data-result-template") || 'Matches for "__query__": __count__.';

    function inboxHaystack(item) {
      return [
        item.getAttribute("data-inbox-type") || "",
        item.getAttribute("data-inbox-label") || "",
        item.getAttribute("data-inbox-project") || "",
        item.textContent || ""
      ].join(" ").toLowerCase();
    }

    function updateInboxFilter() {
      var query = (inboxInput.value || "").trim().toLowerCase();
      var terms = searchTerms(query);
      var visible = 0;

      inboxItems.forEach(function (item) {
        var haystack = inboxHaystack(item);
        var isMatch = !query || terms.some(function (term) {
          return haystack.indexOf(term) !== -1;
        });
        item.hidden = !isMatch;
        if (isMatch) {
          visible += 1;
        }
      });

      inboxGroups.forEach(function (group) {
        var visibleInGroup = Array.prototype.slice.call(group.querySelectorAll("[data-inbox-item]")).some(function (item) {
          return !item.hidden;
        });
        group.hidden = !visibleInGroup;
      });

      if (inboxResult) {
        inboxResult.textContent = query
          ? fillTemplate(inboxResultTemplate, visible, inboxInput.value.trim())
          : fillTemplate(inboxShowingTemplate, visible, "");
      }
      if (inboxEmpty) {
        inboxEmpty.hidden = visible !== 0;
      }
      if (inboxClear) {
        inboxClear.hidden = !query;
      }
    }

    if (inboxInput) {
      inboxInput.addEventListener("input", updateInboxFilter);
      inboxInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          inboxInput.blur();
        }
      });
      if (inboxClear) {
        inboxClear.addEventListener("click", function () {
          inboxInput.value = "";
          updateInboxFilter();
          inboxInput.blur();
        });
      }
      updateInboxFilter();
    }
  }
}());
