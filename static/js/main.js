// static/js/main.js
// Robust AJAX prediction handler — shows prediction or error, updates history
document.addEventListener("DOMContentLoaded", () => {
  console.log("Dashboard loaded ✅");

  // neon glow for buttons
  const buttons = document.querySelectorAll("button");
  buttons.forEach(btn => {
    btn.addEventListener("mousemove", e => {
      const rect = btn.getBoundingClientRect();
      btn.style.setProperty("--x", `${e.clientX - rect.left}px`);
      btn.style.setProperty("--y", `${e.clientY - rect.top}px`);
    });
  });

  const form = document.getElementById("predictionForm");
  const resultBox = document.getElementById("predictionResult");
  const historyTable = document.querySelector(".table tbody");

  // helper to show result nicely
  function showResult(text, type = "info") {
    resultBox.style.display = "inline-block";
    resultBox.style.opacity = "1";
    resultBox.classList.remove("loading", "fake", "real");

    if (type === "fake") {
      resultBox.innerHTML = `⚠️ <strong style="color:#ff6b6b">${text}</strong>`;
      resultBox.classList.add("fake");
    } else if (type === "real") {
      resultBox.innerHTML = `✅ <strong style="color:#4cd964">${text}</strong>`;
      resultBox.classList.add("real");
    } else if (type === "error") {
      resultBox.innerHTML = `⚠️ <strong style="color:#ff6b6b">${text}</strong>`;
    } else {
      resultBox.innerText = text;
    }
  }

  // convenience: hide after some time
  function autoHideResult(ms = 6000) {
    setTimeout(() => {
      resultBox.style.opacity = "0";
      setTimeout(() => {
        resultBox.style.display = "none";
        resultBox.classList.remove("fake", "real");
      }, 600);
    }, ms);
  }

  // Update history table UI by prepending the new row
  function prependHistoryRow(textPreview, prediction) {
    if (!historyTable) return;
    const tr = document.createElement("tr");
    const now = new Date();
    const ts = now.toISOString().slice(0, 19).replace("T", " ");
    tr.innerHTML = `
      <td>New</td>
      <td class="truncate">${textPreview}</td>
      <td><strong>${prediction}</strong></td>
      <td>${ts}</td>
    `;
    historyTable.prepend(tr);
  }

  if (!form || !resultBox) {
    console.warn("Prediction form or result box not found on page.");
    return;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const formData = new FormData(form);
    const textVal = (formData.get("text") || "").toString().trim();

    if (!textVal) {
      showResult("Please enter job details in the textarea.", "error");
      return;
    }

    // show loading
    resultBox.style.display = "inline-block";
    resultBox.classList.add("loading");
    resultBox.innerText = "⏳ Predicting...";
    resultBox.style.opacity = "1";

    try {
      // ✅ ensure cookie-based session is sent
      const res = await fetch(form.action, {
        method: "POST",
        body: formData,
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "include" // <-- REQUIRED for Flask-Login session
      });

      // check for redirect (login page)
      if (res.redirected) {
        showResult("Session expired — please login again.", "error");
        resultBox.classList.remove("loading");
        return;
      }

      const bodyText = await res.text();

      // Detect HTML redirect response
      if (bodyText.trim().startsWith("<")) {
        console.warn("Received HTML. Possibly logged out.");
        showResult("Session expired or redirect occurred — please login again.", "error");
        resultBox.classList.remove("loading");
        return;
      }

      // Parse JSON safely
      let data;
      try {
        data = JSON.parse(bodyText);
      } catch (err) {
        console.error("Failed to parse JSON from server:", bodyText);
        showResult("Unexpected server response. Check console.", "error");
        resultBox.classList.remove("loading");
        return;
      }

      if (data.error) {
        console.error("Server returned error:", data.error);
        showResult(data.error, "error");
        resultBox.classList.remove("loading");
        autoHideResult(6000);
        return;
      }

      if (data.prediction) {
        const pred = data.prediction;
        const predLower = pred.toLowerCase();
        if (predLower.includes("fake") || predLower.includes("fraud")) {
          showResult(pred, "fake");
        } else if (predLower.includes("real") || predLower.includes("genuine") || predLower.includes("ham")) {
          showResult(pred, "real");
        } else {
          showResult(pred, "info");
        }

        // Add to history instantly
        const preview = textVal.replace(/\s+/g, " ").slice(0, 140);
        prependHistoryRow(preview + (preview.length < textVal.length ? "…" : ""), pred);

        resultBox.classList.remove("loading");
        autoHideResult(8000);
        return;
      }

      showResult("No prediction returned from server.", "error");
      resultBox.classList.remove("loading");
      autoHideResult(6000);

    } catch (networkErr) {
      console.error("Fetch failed:", networkErr);
      showResult("Network error while contacting server.", "error");
      resultBox.classList.remove("loading");
      autoHideResult(8000);
    }
  });
});
