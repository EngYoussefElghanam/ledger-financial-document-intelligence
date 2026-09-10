import * as pdfjsLib from "/assets/pdfjs/build/pdf.mjs";
import {
  EventBus,
  PDFFindController,
  PDFLinkService,
  PDFViewer,
} from "/assets/pdfjs/web/pdf_viewer.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/assets/pdfjs/build/pdf.worker.mjs";

const params = new URLSearchParams(window.location.search);
const file = params.get("file");
const hash = new URLSearchParams(window.location.hash.slice(1));
const initialPage = Math.max(1, Number.parseInt(hash.get("page") || "1", 10) || 1);
const initialSearch = (hash.get("search") || "").trim();

const eventBus = new EventBus();
const linkService = new PDFLinkService({ eventBus });
const findController = new PDFFindController({ eventBus, linkService });
const container = document.getElementById("viewer-container");
const viewer = new PDFViewer({
  container,
  eventBus,
  linkService,
  findController,
  textLayerMode: 1,
});
linkService.setViewer(viewer);

const pageNumber = document.getElementById("page-number");
const pageCount = document.getElementById("page-count");
const searchInput = document.getElementById("search");
const matchCount = document.getElementById("match-count");
const status = document.getElementById("status");
const download = document.getElementById("download");
let usingKeywordFallback = false;

function runSearch(findPrevious = false, type = "", queryOverride = null) {
  const query = queryOverride ?? searchInput.value.trim();
  if (!query) return;
  if (queryOverride === null && type !== "again") usingKeywordFallback = false;
  eventBus.dispatch("find", {
    source: window,
    type,
    query,
    phraseSearch: true,
    caseSensitive: false,
    entireWord: false,
    highlightAll: true,
    findPrevious,
    matchDiacritics: false,
  });
}

eventBus.on("pagesinit", () => {
  viewer.currentScaleValue = "page-width";
  viewer.currentPageNumber = Math.min(initialPage, viewer.pagesCount);
  pageNumber.value = viewer.currentPageNumber;
  pageCount.textContent = `/ ${viewer.pagesCount}`;
  status.hidden = true;
  if (initialSearch) {
    searchInput.value = initialSearch;
    // Wait for text layers to start rendering before dispatching find.
    requestAnimationFrame(() => runSearch(false));
  }
});

eventBus.on("pagechanging", ({ pageNumber: current }) => { pageNumber.value = current; });
eventBus.on("updatefindmatchescount", ({ matchesCount }) => {
  if (!matchesCount.total && !usingKeywordFallback) {
    const stopWords = new Set(["and", "are", "for", "from", "that", "the", "this", "was", "were", "with"]);
    const words = [...new Set((searchInput.value.match(/[\p{L}\p{N}$,.%-]+/gu) || [])
      .map(word => word.replace(/^[,.]+|[,.]+$/g, ""))
      .filter(word => word.length >= 4 && !stopWords.has(word.toLowerCase())))]
      .slice(0, 8);
    if (words.length) {
      usingKeywordFallback = true;
      matchCount.textContent = "Finding keywords…";
      runSearch(false, "", words);
      return;
    }
  }
  matchCount.textContent = matchesCount.total ? `${matchesCount.current} / ${matchesCount.total}` : "No matches";
});

document.getElementById("previous").addEventListener("click", () => {
  viewer.currentPageNumber = Math.max(1, viewer.currentPageNumber - 1);
});
document.getElementById("next").addEventListener("click", () => {
  viewer.currentPageNumber = Math.min(viewer.pagesCount, viewer.currentPageNumber + 1);
});
document.getElementById("zoom-in").addEventListener("click", () => viewer.increaseScale());
document.getElementById("zoom-out").addEventListener("click", () => viewer.decreaseScale());
document.getElementById("find-next").addEventListener("click", () => runSearch(false, "again"));
document.getElementById("find-previous").addEventListener("click", () => runSearch(true, "again"));
pageNumber.addEventListener("change", () => {
  viewer.currentPageNumber = Math.min(viewer.pagesCount, Math.max(1, Number(pageNumber.value) || 1));
});
searchInput.addEventListener("keydown", event => {
  if (event.key === "Enter") runSearch(event.shiftKey, "again");
});

if (!file || !file.startsWith("/api/documents/") || !file.endsWith("/pdf")) {
  status.textContent = "Invalid or missing PDF URL.";
  status.classList.add("error");
} else {
  download.href = file;
  try {
    const loadingTask = pdfjsLib.getDocument({ url: file });
    const pdf = await loadingTask.promise;
    viewer.setDocument(pdf);
    linkService.setDocument(pdf);
    findController.setDocument(pdf);
  } catch (error) {
    status.textContent = `Could not load PDF: ${error.message}`;
    status.classList.add("error");
  }
}
