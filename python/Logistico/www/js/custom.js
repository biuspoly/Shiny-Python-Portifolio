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

      var aguardando = modulo.querySelector(".pagina-aguardando-dados");
      if (aguardando) {

        var mensagem = aguardando.getAttribute("data-mensagem");
        if (mensagem) {
          var texto = modulo.querySelector(".pagina-carregando-texto");
          if (texto && texto.textContent !== mensagem) texto.textContent = mensagem;
        }
        return false;
      }
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
  if (parseFloat(window.getComputedStyle(alvo).opacity) > 0.99) return;
  alvo.classList.add("recalculando-fim");
  window.setTimeout(function () {
    alvo.classList.remove("recalculando-fim");
  }, 250);
});

(function () {

  var alvo = "";
  var caixaAnterior = null;
  var assinaturaAnterior = "";

  function assinaturaDa(caixa) {
    return [
      caixa.querySelectorAll(".chat-flutuante-bolha-bot:not(.chat-flutuante-pensando)").length,
      caixa.querySelectorAll(".chat-flutuante-bolha-usuario").length,
      caixa.querySelectorAll(".chat-flutuante-grupo").length,
      caixa.querySelector(".chat-flutuante-grupo.aberto") ? 1 : 0,
      caixa.querySelector(".chat-flutuante-contatos") ? 1 : 0,
      caixa.querySelector(".chat-flutuante-pensando") ? 1 : 0,
      caixa.querySelector(".chat-flutuante-vazio") ? 1 : 0,
    ].join("|");
  }

  function decidirAlvo(antes, agora) {
    var a = antes.split("|");
    var b = agora.split("|");
    var eraVazio = antes === "";

    if (eraVazio) return b[6] === "1" ? "topo" : "fim";
    if (b[5] === "1" && a[5] !== "1") return "fim";
    if (b[0] > a[0]) return "pergunta";
    if (b[3] === "1" && a[3] !== "1") return "grupo";
    if (b[4] === "1" && a[4] !== "1") return "fim";
    if (b[2] > a[2]) return "fim";
    return alvo;
  }

  function aplicarAlvo(caixa) {
    if (alvo === "topo") {
      caixa.scrollTop = 0;
      alvo = "";
      return;
    }
    if (alvo === "fim") {
      caixa.scrollTop = caixa.scrollHeight;
      return;
    }
    if (alvo === "grupo") {
      var grupo = caixa.querySelector(".chat-flutuante-grupo.aberto");
      if (grupo) {

        caixa.scrollTop +=
          grupo.getBoundingClientRect().top - caixa.getBoundingClientRect().top - 8;
      }
      return;
    }
    if (alvo === "pergunta") {

      var perguntas = caixa.querySelectorAll(".chat-flutuante-bolha-usuario");
      if (perguntas.length) {
        var ultima = perguntas[perguntas.length - 1];
        caixa.scrollTop +=
          ultima.getBoundingClientRect().top - caixa.getBoundingClientRect().top;
      }
    }
  }

  function rolarChatParaBaixo() {
    var caixa = document.querySelector(".chat-flutuante-mensagens");
    if (!caixa) {

      if (!document.getElementById("chat_flutuante_painel")) {
        assinaturaAnterior = "";
        alvo = "";
      }
      return;
    }
    var agora = assinaturaDa(caixa);
    var caixaNova = caixa !== caixaAnterior;
    caixaAnterior = caixa;
    if (agora === assinaturaAnterior) {

      if (caixaNova) aplicarAlvo(caixa);
      return;
    }
    alvo = decidirAlvo(assinaturaAnterior, agora);
    assinaturaAnterior = agora;
    aplicarAlvo(caixa);

    window.requestAnimationFrame(function () {
      var atual = document.querySelector(".chat-flutuante-mensagens");
      if (atual) aplicarAlvo(atual);
    });
  }

  new MutationObserver(rolarChatParaBaixo).observe(document.body, {
    childList: true,
    subtree: true,
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Enter" || evento.shiftKey) return;
    if (!evento.target || evento.target.id !== "chat_pergunta") return;
    evento.preventDefault();
    var botaoEnviar = document.getElementById("chat_enviar");
    if (!botaoEnviar || botaoEnviar.disabled) return;

    if (window.Shiny && Shiny.setInputValue) {
      Shiny.setInputValue("chat_pergunta", evento.target.value, { priority: "event" });
    }
    botaoEnviar.click();
  });

  document.addEventListener("mousedown", function (evento) {
    if (!document.getElementById("chat_flutuante_painel")) return;
    var alvo = evento.target;
    if (!alvo || !alvo.closest) return;

    if (alvo.closest("#chat_flutuante_painel")) return;
    if (alvo.closest(".chat-flutuante-botao")) return;
    if (alvo.closest(".modal")) return;
    var fechar = document.getElementById("chat_fechar");
    if (fechar) fechar.click();
  });
})();

(function () {
  var HTML_PENSANDO =
    '<div class="chat-flutuante-bolha chat-flutuante-bolha-bot chat-flutuante-pensando" ' +
    'id="chat-flutuante-pensando-js"><span>Pensando</span>' +
    '<span class="chat-flutuante-pontos">' +
    '<span class="chat-flutuante-ponto"></span>' +
    '<span class="chat-flutuante-ponto"></span>' +
    '<span class="chat-flutuante-ponto"></span>' +
    "</span></div>";

  function mostrarPensando() {
    var pergunta = document.getElementById("chat_pergunta");
    if (!pergunta || !pergunta.value.trim()) return;
    var caixa = document.querySelector(".chat-flutuante-mensagens");
    if (!caixa || document.getElementById("chat-flutuante-pensando-js")) return;
    caixa.insertAdjacentHTML("beforeend", HTML_PENSANDO);
    caixa.scrollTop = caixa.scrollHeight;
  }

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest("#chat_enviar");
    if (!botao || botao.disabled) return;
    mostrarPensando();
  });

  var MS_POR_PALAVRA = 40;
  var DURACAO_MIN_MS = 400;
  var DURACAO_MAX_MS = 2600;
  var respostasReveladas = 0;
  var animacao = null;

  function acompanharRolagem() {
    var caixa = document.querySelector(".chat-flutuante-mensagens");
    if (caixa) caixa.scrollTop = caixa.scrollHeight;
  }

  function nosDeTexto(bolha) {
    var nos = [];
    var caminho = document.createTreeWalker(bolha, NodeFilter.SHOW_TEXT, {
      acceptNode: function (no) {

        if (no.parentElement.closest(".chat-flutuante-tabela, .chat-flutuante-grafico, .chat-flutuante-imagens, .chat-flutuante-arquivos")) {
          return NodeFilter.FILTER_REJECT;
        }
        return no.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    var no;
    while ((no = caminho.nextNode())) nos.push(no);
    return nos;
  }

  function revelarPalavraPorPalavra(bolha) {
    var nos = nosDeTexto(bolha);
    if (!nos.length) return;

    var extras = bolha.querySelectorAll(
      ".chat-flutuante-tabela, .chat-flutuante-grafico, .chat-flutuante-imagens, .chat-flutuante-arquivos"
    );
    var i;
    for (i = 0; i < extras.length; i++) extras[i].style.visibility = "hidden";

    var filas = nos.map(function (no) {

      var partes = no.nodeValue.match(/\s*\S+\s*/g) || [];
      no.nodeValue = "";
      return { no: no, partes: partes, proxima: 0 };
    });
    var total = filas.reduce(function (soma, fila) {
      return soma + fila.partes.length;
    }, 0);
    var duracao = Math.min(DURACAO_MAX_MS, Math.max(DURACAO_MIN_MS, total * MS_POR_PALAVRA));

    var atual = 0;
    var reveladas = 0;

    function terminar() {
      animacao = null;
      filas.forEach(function (fila) {
        fila.no.nodeValue = fila.partes.join("");
      });
      for (var j = 0; j < extras.length; j++) extras[j].style.visibility = "";
      acompanharRolagem();
    }

    var inicio = performance.now();
    function quadro(agora) {

      if (!bolha.isConnected) {
        animacao = null;
        return;
      }
      var progresso = Math.min(1, (agora - inicio) / duracao);
      var alvo = Math.ceil(progresso * total);
      while (reveladas < alvo) {
        var fila = filas[atual];
        while (fila && fila.proxima >= fila.partes.length) fila = filas[++atual];
        if (!fila) break;
        fila.no.nodeValue += fila.partes[fila.proxima++];
        reveladas++;
      }
      acompanharRolagem();
      if (progresso < 1) {
        animacao = { id: window.requestAnimationFrame(quadro), terminar: terminar };
      } else {
        terminar();
      }
    }
    animacao = { id: window.requestAnimationFrame(quadro), terminar: terminar };
  }

  function revelarRespostaNova() {
    var caixa = document.querySelector(".chat-flutuante-mensagens");
    if (!caixa) {
      respostasReveladas = 0;
      return;
    }
    var bolhas = caixa.querySelectorAll(
      ".chat-flutuante-bolha-bot:not(.chat-flutuante-pensando)"
    );
    if (bolhas.length <= respostasReveladas) {
      respostasReveladas = bolhas.length;
      return;
    }
    respostasReveladas = bolhas.length;

    if (animacao) {
      window.cancelAnimationFrame(animacao.id);
      animacao.terminar();
    }
    revelarPalavraPorPalavra(bolhas[bolhas.length - 1]);
  }

  new MutationObserver(revelarRespostaNova).observe(document.body, {
    childList: true,
    subtree: true,
  });

  function prepararLinkZap(alvo) {
    var enviar = alvo && alvo.closest ? alvo.closest(".chat-flutuante-enviar-zap") : null;
    if (!enviar) return;
    var base = enviar.dataset.base || "";
    if (!base) return;
    var campo = document.getElementById("chat_pergunta");
    var texto = campo ? campo.value.trim() : "";
    enviar.href = base.replace(
      "__MENSAGEM__",
      encodeURIComponent(texto || "(sem mensagem escrita)")
    );
  }

  document.addEventListener("mousedown", function (evento) {
    prepararLinkZap(evento.target);
  });
  document.addEventListener("click", function (evento) {
    prepararLinkZap(evento.target);
  });

  document.addEventListener("click", function (evento) {
    if (!window.Shiny || !Shiny.setInputValue) return;

    var contato = evento.target.closest(".chat-flutuante-contato[data-canal]");
    if (contato) {
      if (!contato.classList.contains("desativado")) {
        Shiny.setInputValue("chat_canal", contato.dataset.canal, { priority: "event" });
      }
      return;
    }
    var grupo = evento.target.closest(".chat-flutuante-grupo");
    if (grupo) {
      Shiny.setInputValue("chat_grupo", grupo.dataset.grupo, { priority: "event" });
      return;
    }
    var chip = evento.target.closest(".chat-flutuante-sugestao");
    if (chip) {
      Shiny.setInputValue("chat_tema", chip.textContent.trim(), { priority: "event" });
    }
  });

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
