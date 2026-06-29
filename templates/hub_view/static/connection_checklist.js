(function () {
  var connectionChecklist = document.querySelector("[data-connection-checklist]");
  if (connectionChecklist) {
    var connectionChecks = Array.prototype.slice.call(connectionChecklist.querySelectorAll("[data-connection-check]"));
    var connectionSummary = connectionChecklist.querySelector("[data-connection-summary]");
    var summaryTemplate = connectionChecklist.getAttribute("data-summary-template") || "Manual checks completed: __done__ of __total__.";
    var openLabel = connectionChecklist.getAttribute("data-open-label") || "Still open";
    var readyLabel = connectionChecklist.getAttribute("data-ready-label") || "Looks ready";

    function fillCheckTemplate(template, done, total) {
      return template
        .replace(/__done__/g, String(done))
        .replace(/__total__/g, String(total));
    }

    function updateConnectionChecklist() {
      var done = connectionChecks.filter(function (item) {
        return item.checked;
      }).length;
      if (connectionSummary) {
        connectionSummary.textContent = fillCheckTemplate(summaryTemplate, done, connectionChecks.length);
      }
      Array.prototype.slice.call(connectionChecklist.querySelectorAll("[data-connection-check-card]")).forEach(function (card) {
        var cardChecks = Array.prototype.slice.call(card.querySelectorAll("[data-connection-check]"));
        var cardDone = cardChecks.length > 0 && cardChecks.every(function (item) {
          return item.checked;
        });
        var cardState = card.querySelector("[data-check-card-state]");
        card.classList.toggle("done", cardDone);
        if (cardState) {
          cardState.textContent = cardDone ? readyLabel : openLabel;
        }
      });
    }

    connectionChecks.forEach(function (item) {
      item.addEventListener("change", updateConnectionChecklist);
    });
    updateConnectionChecklist();
  }
}());
