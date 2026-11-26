document.addEventListener("DOMContentLoaded", function () {

  const layout = document.querySelector(".bslib-sidebar-layout");

  const toggle = layout.querySelector(".collapse-toggle");

  const telaDesktop = window.matchMedia("(min-width: 576px)");

  if (telaDesktop.matches) layout.classList.add("mini-sidebar");

  toggle.addEventListener(
    "click",
    function (e) {

      if (!telaDesktop.matches) return;

      e.stopImmediatePropagation();

      layout.classList.toggle("mini-sidebar");
    },
    true
  );

  function cabecalhoDoGrupo(botao) {
    const itemAccordion = botao.closest(".accordion-item");
    if (!itemAccordion) return null;
    return itemAccordion.querySelector(".accordion-button");
  }

  document.querySelectorAll(".sidebar .action-button.selecionado").forEach(function (botao) {
    const cabecalho = cabecalhoDoGrupo(botao);
    if (cabecalho) cabecalho.classList.add("selecionado");
  });

  document.addEventListener("click", function (e) {
    const botao = e.target.closest(".sidebar .action-button");
    if (!botao) return;

    document.querySelectorAll(".sidebar .selecionado").forEach(function (el) {
      el.classList.remove("selecionado");
    });

    botao.classList.add("selecionado");

    const cabecalho = cabecalhoDoGrupo(botao);
    if (cabecalho) cabecalho.classList.add("selecionado");
  });
});

document.addEventListener("DOMContentLoaded", function () {
  window.setTimeout(function () {
    document.body.classList.add("pronto");
  }, 150);
});

(function () {
  var permissaoPedida = false;
  var pendentes = 0;
  var tituloOriginal = document.title;

  function suportado() {
    return typeof window.Notification !== "undefined";
  }

  function pedirPermissao() {
    if (permissaoPedida || !suportado()) return;
    permissaoPedida = true;
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  }

  ["click", "keydown"].forEach(function (evento) {
    document.addEventListener(evento, pedirPermissao, { once: true });
  });

  function marcarNoTitulo() {
    pendentes += 1;
    document.title = "(" + pendentes + ") " + tituloOriginal;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") return;
    pendentes = 0;
    document.title = tituloOriginal;
  });

  function mostrar(dados) {
    var quantos = dados.quantos || 1;
    var titulo = quantos > 1
      ? quantos + " erros novos -- " + dados.app
      : "Erro novo em " + dados.app;
    var corpo = (dados.onde ? dados.onde + ": " : "") + (dados.mensagem || "");
    marcarNoTitulo();
    if (!suportado() || Notification.permission !== "granted") return;
    try {
      var aviso = new Notification(titulo, {
        body: corpo,

        tag: "monitoramento-erro-" + dados.app,
        requireInteraction: false,
      });
      aviso.onclick = function () {
        window.focus();
        aviso.close();
      };
    } catch (erro) {

    }
  }

  if (window.Shiny && Shiny.addCustomMessageHandler) {
    Shiny.addCustomMessageHandler("avisoErroNovo", mostrar);
  }
})();

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
