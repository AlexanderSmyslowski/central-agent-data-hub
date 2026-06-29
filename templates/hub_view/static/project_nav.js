(function () {
  var projectSectionNav = document.querySelector("[data-project-section-nav]");
  if (projectSectionNav) {
    var sectionLinks = Array.prototype.slice.call(projectSectionNav.querySelectorAll("[data-section-target]"));
    var sectionTargets = sectionLinks.map(function (link) {
      return {
        id: link.getAttribute("data-section-target"),
        link: link,
        element: document.getElementById(link.getAttribute("data-section-target"))
      };
    }).filter(function (item) {
      return item.element;
    });
    var sectionFrame = null;

    function setActiveProjectSection(activeId) {
      sectionTargets.forEach(function (item) {
        var isActive = item.id === activeId;
        var wasActive = item.link.classList.contains("active");
        item.link.classList.toggle("active", isActive);
        if (isActive) {
          item.link.setAttribute("aria-current", "location");
          if (!wasActive) {
            item.link.scrollIntoView({ inline: "center", block: "nearest", behavior: "auto" });
          }
        } else {
          item.link.removeAttribute("aria-current");
        }
      });
    }

    function updateProjectSectionNav() {
      if (!sectionTargets.length) {
        return;
      }
      var activationLine = projectSectionNav.getBoundingClientRect().bottom + 96;
      var sortedTargets = sectionTargets.slice().sort(function (left, right) {
        return left.element.getBoundingClientRect().top - right.element.getBoundingClientRect().top;
      });
      var active = sortedTargets[0];
      sortedTargets.forEach(function (item) {
        if (item.element.getBoundingClientRect().top <= activationLine) {
          active = item;
        }
      });
      setActiveProjectSection(active.id);
    }

    function requestProjectSectionUpdate() {
      if (sectionFrame) {
        return;
      }
      sectionFrame = window.requestAnimationFrame(function () {
        sectionFrame = null;
        updateProjectSectionNav();
      });
    }

    sectionLinks.forEach(function (link) {
      link.addEventListener("click", function () {
        var targetId = link.getAttribute("data-section-target");
        if (targetId) {
          setActiveProjectSection(targetId);
        }
      });
    });
    window.addEventListener("scroll", requestProjectSectionUpdate, { passive: true });
    window.addEventListener("resize", requestProjectSectionUpdate);
    window.addEventListener("hashchange", requestProjectSectionUpdate);
    updateProjectSectionNav();
  }
}());
