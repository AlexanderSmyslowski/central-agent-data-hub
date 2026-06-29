(function () {
  var reviewSearchAliases = {
    risiko: ["risk", "risks", "risiken"],
    risiken: ["risk", "risks", "risiko"],
    frage: ["question", "questions", "open question", "offene fragen"],
    fragen: ["question", "questions", "open question", "offene fragen"],
    entscheidung: ["decision", "decisions"],
    entscheidungen: ["decision", "decisions"],
    fakt: ["fact", "facts", "fakten"],
    fakten: ["fact", "facts", "fakt"],
    bericht: ["report", "reports", "status", "stand"],
    berichte: ["report", "reports", "status", "stand"],
    stand: ["status", "latest status", "report", "bericht"],
    arbeitsstand: ["status", "latest status", "report", "bericht"],
    beziehung: ["relation", "relations", "beziehungen"],
    beziehungen: ["relation", "relations", "beziehung"],
    quelle: ["source", "sources"],
    quellen: ["source", "sources"],
    pruefung: ["review", "reviewed", "draft", "drafts"],
    prüfung: ["review", "reviewed", "draft", "drafts"],
    zuständig: ["reviewer", "owner"],
    zustaendig: ["reviewer", "owner"]
  };

  function searchTerms(query) {
    var terms = [query];
    query.split(/\s+/).forEach(function (word) {
      if (reviewSearchAliases[word]) {
        terms = terms.concat(reviewSearchAliases[word]);
      }
    });
    if (reviewSearchAliases[query]) {
      terms = terms.concat(reviewSearchAliases[query]);
    }
    return terms.filter(function (term, index) {
      return term && terms.indexOf(term) === index;
    });
  }

  function fillTemplate(template, count, query) {
    return template
      .replace(/__count__/g, String(count))
      .replace(/__query__/g, query || "");
  }
  window.ADHHubView = window.ADHHubView || {};
  window.ADHHubView.searchTerms = searchTerms;
  window.ADHHubView.fillTemplate = fillTemplate;
}());
