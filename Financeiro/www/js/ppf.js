(function () {
  var teto = null;

  var RESTAURADA = "ppfHistoricoRestaurado";
  var CICLO_MS = 120000;

  function historicoNaUrl(valor) {
    var url = new URL(window.location.href);
    if (valor) url.searchParams.set("historico", valor);
    else url.searchParams.delete("historico");
    if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url.href);
  }

  function lerRestaurada() {
    try { return JSON.parse(window.sessionStorage.getItem(RESTAURADA) || "null"); }
    catch (e) { return null; }
  }

  var naUrl = new URL(window.location.href).searchParams.get("historico") || "";
  var restaurando = "";
  if (naUrl) {
    var antes = lerRestaurada();
    if (antes && antes.valor === naUrl && Date.now() - antes.quando < CICLO_MS) {
      window.sessionStorage.removeItem(RESTAURADA);
      historicoNaUrl("");
    } else {
      window.sessionStorage.setItem(RESTAURADA, JSON.stringify({ valor: naUrl, quando: Date.now() }));
      restaurando = naUrl;
    }
  }

  function caixa() {
    var fundo = document.getElementById("ppf-carregando-historico");
    if (!fundo) {
      fundo = document.createElement("div");
      fundo.id = "ppf-carregando-historico";
      fundo.className = "ppf-carregando-historico-fundo";
      fundo.hidden = true;
      fundo.innerHTML =
        '<div class="ppf-carregando-historico" role="status">' +
        '<div class="spinner-border"></div>' +
        '<span class="pagina-carregando-texto"></span></div>';
      document.body.appendChild(fundo);
    }
    return fundo;
  }

  function fechar() {
    window.clearTimeout(teto);
    var fundo = document.getElementById("ppf-carregando-historico");
    if (fundo) fundo.hidden = true;
  }

  function abrir(texto) {
    var fundo = caixa();
    fundo.querySelector(".pagina-carregando-texto").textContent = texto;
    fundo.hidden = false;
    window.clearTimeout(teto);
    teto = window.setTimeout(fechar, 60000);
  }

  if (restaurando) {
    var partes = restaurando.split("-");
    var abrirRestaurada = function () {
      abrir("Carregando o histórico de " + partes[2] + "/" + partes[1] + "/" + partes[0] + "...");
    };
    if (document.body) abrirRestaurada();
    else document.addEventListener("DOMContentLoaded", abrirRestaurada);
  }

  $(document).on("change", "#diario-historico", function (e) {

    historicoNaUrl(this.value);

    if (!e.originalEvent) return;
    var dia = this.value ? this.options[this.selectedIndex].text : "";
    abrir(dia ? "Carregando o histórico de " + dia + "..." : "Carregando a posição atual...");
  });

  if (window.Shiny && Shiny.addCustomMessageHandler) {

    Shiny.addCustomMessageHandler("fecharCarregandoHistorico", function (_recado) {

      window.sessionStorage.removeItem(RESTAURADA);
      fechar();
    });

    var somadas = null, vigiada = null;
    function destacar() {
      var grade = somadas && document.getElementById(somadas.grade);
      if (!grade) return;
      var linhas = grade.querySelectorAll("tbody tr");
      grade.querySelectorAll("td.ppf-cel-somada, td.ppf-cel-somavel").forEach(function (td) {
        td.classList.remove("ppf-cel-somada", "ppf-cel-somavel");
      });
      somadas.somaveis.forEach(function (l) {
        var tr = linhas[l];
        if (!tr) return;
        for (var c = 1; c < tr.cells.length; c++) tr.cells[c].classList.add("ppf-cel-somavel");
      });
      somadas.celulas.forEach(function (lc) {
        var tr = linhas[lc[0]];
        if (tr && tr.cells[lc[1]]) tr.cells[lc[1]].classList.add("ppf-cel-somada");
      });
      if (vigiada !== grade) {
        vigiada = grade;
        new MutationObserver(function () { window.requestAnimationFrame(destacar); })
          .observe(grade, { childList: true, subtree: true });
      }
    }
    Shiny.addCustomMessageHandler("ppfCelulasSomadas", function (recado) {
      somadas = recado;
      destacar();
    });

    $(document).on("shiny:value", function (e) {
      if (somadas && e.target && e.target.id === somadas.grade) window.setTimeout(destacar, 100);
    });
    document.addEventListener("click", function (e) {
      if (!somadas || !(e.ctrlKey || e.metaKey)) return;
      var td = e.target.closest && e.target.closest("td.ppf-cel-somavel");
      if (!td) return;
      var tr = td.parentElement;
      e.preventDefault();
      Shiny.setInputValue(somadas.clique, {
        linha: Array.prototype.indexOf.call(tr.parentElement.children, tr),
        coluna: Array.prototype.indexOf.call(tr.children, td),
      }, { priority: "event" });
    });

    Shiny.addCustomMessageHandler("ppfVistos", function (recados) {
      recados.forEach(function (r) {
        var celula = document.querySelector('.ppf-cel-visto[data-visto="' + r.visto + '"]');
        if (!celula) return;
        celula.setAttribute("data-quem", r.quem || "");
        var caixa = celula.querySelector('input[type="checkbox"]');
        if (!caixa || caixa.checked === r.marcado) return;
        caixa.checked = r.marcado;
        if (!caixa.classList.contains("ppf-visto-travado")) $(caixa).trigger("change");
      });
    });
  }
})();

document.addEventListener("mouseover", function (evento) {
  var celula = evento.target.closest && evento.target.closest(".ppf-cel-fornecedor");
  if (!celula) return;
  var balao = celula.querySelector(".ppf-tooltip-pagos");
  if (!balao) return;
  var r = celula.getBoundingClientRect();
  var largura = balao.offsetWidth, altura = balao.offsetHeight;
  var esquerda = Math.min(r.left + 214, window.innerWidth - largura - 8);
  var topo = r.top + altura > window.innerHeight - 8 ? Math.max(8, r.bottom - altura) : r.top;
  balao.style.left = Math.round(Math.max(8, esquerda)) + "px";
  balao.style.top = Math.round(topo) + "px";
});

document.addEventListener("click", function (e) {
  var rotulo = e.target.closest && e.target.closest(".crec-timeline label");
  if (!rotulo || e.ctrlKey || e.metaKey) return;
  var caixa = rotulo.querySelector('input[type="checkbox"]');
  var grupo = rotulo.closest(".shiny-options-group");
  if (!caixa || !grupo) return;
  var outras = Array.prototype.filter.call(grupo.querySelectorAll('input[type="checkbox"]'),
    function (c) { return c !== caixa && c.checked; });
  if (!outras.length) return;
  outras.forEach(function (c) { c.checked = false; });
  if (caixa.checked) {
    e.preventDefault();
    $(caixa).trigger("change");
  }
}, true);

(function () {
  function campo(alvo) {
    if (!alvo || alvo.tagName !== "INPUT" || alvo.type !== "text" || alvo.disabled) return null;
    return alvo.closest(".campo-reais, .campo-reais-cru") ? alvo : null;
  }
  function numero(texto) {
    var t = String(texto || "").replace(/R\$/g, "").replace(/\s/g, "");
    if (!t) return null;
    var v = t.lastIndexOf(","), p = t.lastIndexOf(".");
    if (v >= 0 && p >= 0) t = v > p ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
    else if (v >= 0) t = t.replace(",", ".");
    else if (p >= 0 && (t.split(".").length > 2 || t.length - p === 4)) t = t.replace(/\./g, "");
    var n = parseFloat(t);
    return isNaN(n) ? null : n;
  }
  document.addEventListener("focus", function (e) {
    var el = campo(e.target);
    if (!el) return;
    var n = numero(el.value);
    if (n !== null) el.value = n.toFixed(2).replace(".", ",");
  }, true);
  document.addEventListener("blur", function (e) {
    var el = campo(e.target);
    if (!el) return;
    var n = numero(el.value);
    if (n === null) return;
    var texto = Math.abs(n).toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    var com_rs = !el.closest(".campo-reais-cru");
    el.value = (n < 0 ? "-" : "") + (com_rs ? "R$ " : "") + texto;
  }, true);

  function atualizarJuros(el) {
    var td = el.closest("td");
    var alvo = td && td.nextElementSibling;
    if (!alvo || !alvo.classList.contains("ppf-cel-juros")) return;
    var original = parseFloat(alvo.getAttribute("data-original"));
    var pago = numero(el.value);
    var juros = (pago === null || isNaN(original)) ? 0 : Math.max(0, Math.round((pago - original) * 100) / 100);
    alvo.textContent = "R$ " + juros.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }
  document.addEventListener("input", function (e) {
    var el = campo(e.target);
    if (el) atualizarJuros(el);
  }, true);

  $(document).on("change", "td.campo-reais input[type=text]", function () { atualizarJuros(this); });
})();

(function () {
  var VALOR = "diario-valor_original_manual", CNPJ = "diario-cnpj_manual";
  document.addEventListener("input", function (e) {
    var campo = e.target, v;
    if (campo.id === VALOR) {
      v = campo.value.replace(/\D/g, "");
      if (!v) return;
      v = (parseInt(v, 10) / 100).toFixed(2).replace(".", ",");
      campo.value = "R$ " + v.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    } else if (campo.id === CNPJ) {
      v = campo.value.replace(/\D/g, "");
      v = v.replace(/^(\d{2})(\d)/, "$1.$2");
      v = v.replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3");
      v = v.replace(/\.(\d{3})(\d)/, ".$1/$2");
      campo.value = v.replace(/(\d{4})(\d)/, "$1-$2");
    }
  }, true);
  document.addEventListener("focusin", function (e) {
    if (e.target.id === VALOR && e.target.value === "R$ 0,00") e.target.value = "";
  });
})();

document.addEventListener("dblclick", function (e) {
  var linha = e.target.closest(".ppf-tabela-manuais tbody tr[data-linha]");
  if (!linha || e.target.closest("button") || !window.Shiny) return;
  var alvo = linha.closest("table").getAttribute("data-input-editar");
  if (alvo) Shiny.setInputValue(alvo, Number(linha.getAttribute("data-linha")), { priority: "event" });
});

document.addEventListener("click", function (e) {
  var seta = e.target.closest && e.target.closest(".fin-btn-abrir[data-entrada]");
  if (!seta || !window.Shiny) return;
  Shiny.setInputValue(seta.getAttribute("data-entrada"),
    { chave: seta.getAttribute("data-chave"), n: Date.now() }, { priority: "event" });
});

document.addEventListener("click", function (e) {
  var botao = e.target.closest && e.target.closest("button.ppf-btn-anexo-fora");
  if (!botao || botao.disabled || !window.Shiny) return;
  Shiny.setInputValue(botao.getAttribute("data-entrada"),
    { id: botao.getAttribute("data-id"), n: Date.now() }, { priority: "event" });
});

document.addEventListener("click", function (e) {
  if (!window.Shiny || !e.target.closest || e.target.closest(".popover")) return;
  var clicado = e.target.closest("td.ppf-cel-auditoria bslib-popover");
  var abertos = [];
  var entrada = null;
  document.querySelectorAll("td.ppf-cel-auditoria bslib-popover").forEach(function (balao) {
    if (balao === clicado || !balao.visible || !balao.id) return;
    var nome = balao.id.match(/pa_balao_\d+$/);
    var botao = balao.querySelector("button.ppf-pa[data-fechar]");
    if (!nome || !botao) return;
    abertos.push(nome[0]);
    entrada = botao.getAttribute("data-fechar");
  });
  if (abertos.length && entrada) {
    Shiny.setInputValue(entrada, { ids: abertos, n: Date.now() }, { priority: "event" });
  }
});

(function () {
  var observado = null;

  function liberar() {
    var botao = document.getElementById("bt_entendi_mudancas");
    if (botao) botao.disabled = false;
    var dica = document.getElementById("mudancas_dica");
    if (dica) dica.textContent = "Pode confirmar.";
  }

  function chegouAoFim(el) {
    return el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
  }

  function ligar() {
    var corpo = document.getElementById("mudancas_texto");
    if (!corpo) {
      observado = null;
      return;
    }
    if (corpo === observado) return;

    if (!corpo.clientHeight) return;
    observado = corpo;

    var fim = corpo.querySelector(".mudancas-fim");
    if (fim && window.IntersectionObserver) {
      new IntersectionObserver(function (entradas, observer) {
        if (!entradas.some(function (e) { return e.isIntersecting; })) return;
        liberar();
        observer.disconnect();
      }, { root: corpo, threshold: 0 }).observe(fim);
    }

    corpo.addEventListener("scroll", function aoRolar() {
      if (!chegouAoFim(corpo)) return;
      liberar();
      corpo.removeEventListener("scroll", aoRolar);
    });

    var modal = corpo.closest(".modal-body") || corpo.closest(".modal");
    if (modal && modal !== corpo) {
      modal.addEventListener("scroll", function aoRolarModal() {
        if (!chegouAoFim(modal)) return;
        liberar();
        modal.removeEventListener("scroll", aoRolarModal);
      });
    }

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (corpo.scrollHeight <= corpo.clientHeight + 2) liberar();
      });
    });
  }

  new MutationObserver(ligar).observe(document.body, { childList: true, subtree: true });
  ligar();
})();

(function () {
  var procurado = "";

  function semAcento(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function filtrar() {
    var corpo = document.querySelector(".ppf-permissoes-corpo");
    if (!corpo) return;
    var campo = corpo.querySelector(".ppf-permissoes-busca");
    if (campo && campo.value !== procurado) campo.value = procurado;
    var alvo = semAcento(procurado.trim());
    corpo.querySelectorAll(".ppf-permissoes-grupo").forEach(function (grupo) {
      var algum = false;
      grupo.querySelectorAll(".ppf-permissoes-item").forEach(function (item) {
        var mostra = !alvo || semAcento(item.getAttribute("data-busca")).indexOf(alvo) !== -1;
        item.style.display = mostra ? "" : "none";
        if (mostra) algum = true;
      });

      grupo.style.display = algum || grupo.querySelector(".ppf-permissoes-busca") ? "" : "none";
    });
  }

  document.addEventListener("input", function (e) {
    if (!e.target.classList || !e.target.classList.contains("ppf-permissoes-busca")) return;
    procurado = e.target.value;
    filtrar();
  });

  $(document).on("shiny:value", function (e) {
    if (e.name && /permissoes_corpo$/.test(e.name)) window.setTimeout(filtrar, 0);
  });

  $(document).on("hidden.bs.modal", function (e) {
    if (e.target && e.target.querySelector && e.target.querySelector(".ppf-permissoes-corpo")) procurado = "";
  });
})();

(function () {
  document.addEventListener("change", function (e) {
    var caixa = e.target;
    if (!caixa || caixa.tagName !== "SELECT" || caixa.id.indexOf("pg_banco_") === -1) return;
    var linha = caixa.closest("tr");
    var icone = linha && linha.querySelector("img.ppf-cel-olho[data-icones]");
    if (!icone) return;
    var destino = (JSON.parse(icone.getAttribute("data-icones") || "{}"))[caixa.value];
    var alvo = destino || icone.getAttribute("data-icone-normal");
    var dono = icone.closest("a, button");
    if (dono) dono.hidden = !alvo;
    if (alvo) icone.setAttribute("src", alvo);
    icone.classList.toggle("ppf-cel-destino", !!destino);
  });
})();
