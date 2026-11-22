document.addEventListener("DOMContentLoaded", function () {
  window.setTimeout(function () {
    document.body.classList.add("pronto");
  }, 150);
});

(function () {

  var TEMPO_MAXIMO_MS = 45000;

  function esconder(modulo) {
    var tela = modulo.querySelector(".pagina-carregando-inicial");
    if (tela) tela.classList.add("pagina-carregando-escondido");
    modulo.dataset.carregamentoResolvido = "1";
  }

  function estaVisivel(modulo) {
    return modulo.offsetParent !== null;
  }

  var valoresRecebidos = new WeakSet();
  jQuery(document).on("shiny:value", function (evento) {
    if (evento.target) valoresRecebidos.add(evento.target);
  });

  function prepararModulo(modulo) {
    if (modulo.dataset.carregamentoPreparado === "1") return;
    if (!estaVisivel(modulo)) return;
    modulo.dataset.carregamentoPreparado = "1";
    window.setTimeout(function () {
      if (modulo.dataset.carregamentoResolvido !== "1") esconder(modulo);
    }, TEMPO_MAXIMO_MS);

    var ESPERA_OCIOSO_MS = 400;
    var timerOcioso = null;

    function tudoPronto() {
      var outputs = modulo.querySelectorAll(".shiny-bound-output");
      if (outputs.length === 0) return false;
      for (var i = 0; i < outputs.length; i++) {
        var el = outputs[i];
        if (el.classList.contains("recalculating")) return false;
        if (!valoresRecebidos.has(el)) return false;
      }
      return true;
    }

    function reavaliar() {
      if (modulo.dataset.carregamentoResolvido === "1") return;
      if (timerOcioso) {
        window.clearTimeout(timerOcioso);
        timerOcioso = null;
      }
      if (!tudoPronto()) return;

      timerOcioso = window.setTimeout(function () {
        if (!tudoPronto()) return;
        esconder(modulo);
        jQuery(document).off("shiny:value", reavaliar);
        observador.disconnect();
      }, ESPERA_OCIOSO_MS);
    }

    jQuery(document).on("shiny:value", reavaliar);
    var observador = new MutationObserver(reavaliar);
    observador.observe(modulo, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    reavaliar();
  }

  function varrerModulos() {
    document.querySelectorAll(".pagina-modulo").forEach(prepararModulo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerModulos();

    new MutationObserver(varrerModulos).observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["style", "class"],
    });
  });
})();

jQuery(document).on("shiny:value", function (evento) {
  var alvo = evento.target;
  if (!alvo || !alvo.closest || !alvo.closest(".pagina-modulo")) return;
  alvo.classList.add("recalculating");
  window.setTimeout(function () {
    alvo.classList.remove("recalculating");
  }, 250);
});

(function () {
  function porExtenso(horas) {
    if (!horas) return "";
    if (horas < 1) {
      var minutos = Math.round(horas * 60);
      return minutos + (minutos === 1 ? " minuto" : " minutos");
    }
    var texto = Number(horas.toFixed(1)).toString().replace(".", ",");
    return texto + (horas === 1 ? " hora" : " horas");
  }

  function mostrar(dados) {
    if (document.getElementById("sessao-expirada")) return;

    var tempo = porExtenso(dados && dados.horas);

    var icone = document.createElement("div");
    icone.className = "sessao-expirada-icone";
    icone.textContent = "!";

    var titulo = document.createElement("div");
    titulo.className = "sessao-expirada-titulo";
    titulo.textContent = "Sessão expirada";

    var texto = document.createElement("div");
    texto.className = "sessao-expirada-texto";
    texto.textContent = tempo
      ? "Esta aba ficou aberta por " + tempo + " e foi encerrada. Recarregue a página para continuar."
      : "Esta aba foi encerrada. Recarregue a página para continuar.";

    var botao = document.createElement("button");
    botao.type = "button";
    botao.className = "sessao-expirada-botao";
    botao.textContent = "Recarregar página";
    botao.addEventListener("click", function () {
      window.location.reload();
    });

    var caixa = document.createElement("div");
    caixa.className = "sessao-expirada-caixa";
    caixa.appendChild(icone);
    caixa.appendChild(titulo);
    caixa.appendChild(texto);
    caixa.appendChild(botao);

    var fundo = document.createElement("div");
    fundo.id = "sessao-expirada";
    fundo.appendChild(caixa);

    document.body.appendChild(fundo);
    botao.focus();
  }

  if (window.Shiny && Shiny.addCustomMessageHandler) {
    Shiny.addCustomMessageHandler("sessaoExpirada", mostrar);
  }
})();

(function () {
  var agendado = false;

  function campoNaTela(controle) {
    var caixa = controle.getBoundingClientRect();
    return caixa.bottom > 0 && caixa.top < (window.innerHeight || document.documentElement.clientHeight);
  }

  function acompanhar() {
    agendado = false;
    document.querySelectorAll(".selectized").forEach(function (campo) {
      var instancia = campo.selectize;
      if (!instancia || !instancia.isOpen) return;

      var controle = (instancia.$control && instancia.$control[0])
        || (campo.parentElement && campo.parentElement.querySelector(".selectize-control"));
      if (controle && !campoNaTela(controle)) {
        instancia.close();
        return;
      }
      instancia.positionDropdown();
    });
  }

  function aoMover(evento) {

    var alvo = evento && evento.target;
    if (alvo && alvo.closest && alvo.closest(".selectize-dropdown")) return;

    if (agendado) return;
    agendado = true;
    requestAnimationFrame(acompanhar);
  }

  document.addEventListener("scroll", aoMover, true);
  window.addEventListener("resize", aoMover);
})();

(function () {
  function instanciaDo(dropdown) {

    var achada = null;
    document.querySelectorAll("select.selectized, input.selectized").forEach(function (el) {
      if (el.selectize && el.selectize.$dropdown && el.selectize.$dropdown[0] === dropdown) {
        achada = el.selectize;
      }
    });
    return achada;
  }

  function engolir(evento) {
    evento.preventDefault();
    evento.stopPropagation();
  }

  document.addEventListener(
    "mouseup",
    function (evento) {
      if (evento.button !== 0) return;
      var opcao = evento.target.closest && evento.target.closest(".selectize-dropdown .option.selected");
      if (!opcao) return;
      var selectize = instanciaDo(opcao.closest(".selectize-dropdown"));

      if (!selectize || selectize.settings.mode !== "multi") return;
      var valor = opcao.getAttribute("data-value");
      if (selectize.items.indexOf(valor) === -1) return;

      evento.preventDefault();
      evento.stopPropagation();
      selectize.removeItem(valor);
      selectize.refreshOptions(false);

      document.addEventListener("click", engolir, { capture: true, once: true });
      window.setTimeout(function () {
        document.removeEventListener("click", engolir, true);
      }, 0);
    },
    true
  );
})();
