const brl = (v) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(v) || 0);
let valorBaseOriginal = 0;
    let custoTempoCalculado = 0;

    async function confirmarExclusao(id, tipo) {
        if (confirm("Deseja realmente excluir este registro?")) {
            try {
                const res = await fetch(`/${tipo}/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    location.reload();
                } else {
                    alert('Erro ao excluir. Tente novamente.');
                }
            } catch(error) {
                alert('Erro de conexão. Verifique sua internet.');
            }
        }
    }

    async function abrirModalFinalizar(lavagemId) {
        try {
            const response = await fetch(`/lavagens/${lavagemId}/dados-finalizacao`);
            if (!response.ok) throw new Error('Falha ao consultar o serviço');
            const data = await response.json();

            valorBaseOriginal = data.valor_base;
            custoTempoCalculado = data.custo_mao_de_obra;

            document.getElementById('txt_valor_base').innerText = brl(data.valor_base);
            document.getElementById('txt_minutos').innerText = data.minutos;
            document.getElementById('txt_custo_tempo').innerText = brl(data.custo_mao_de_obra);
            document.getElementById('input_valor_final').value = data.sugerido.toFixed(2);
            document.getElementById('formFinalizar').action = `/lavagens/${lavagemId}/finalizar`;

            const container = document.getElementById('lista_produtos_modal');
            container.replaceChildren();
            data.todos_produtos.forEach(p => {
                const row = document.createElement('div');
                row.className = 'form-check small mb-2';
                const input = document.createElement('input');
                Object.assign(input, {type: 'checkbox', name: 'produtos_ids', value: p.id, id: `p${p.id}`, checked: p.incluido});
                input.className = 'form-check-input check-produto';
                input.disabled = p.incluido;
                input.dataset.custo = p.custo_por_dose;
                input.addEventListener('change', atualizarSomaTotal);
                const label = document.createElement('label');
                label.className = 'form-check-label';
                label.htmlFor = input.id;
                label.textContent = `${p.nome} · custo ${brl(p.custo_por_dose)}${p.incluido ? ' (incluído no serviço)' : ''}`;
                row.append(input, label);
                container.append(row);
            });
            atualizarSomaTotal();

            new bootstrap.Modal(document.getElementById('modalFinalizar')).show();
        } catch(error) {
            alert('Erro ao carregar dados. Tente novamente.');
            console.error(error);
        }
    }

    function atualizarSomaTotal() {
        let extraProdutos = 0;
        document.querySelectorAll('.check-produto:checked').forEach(c => {
            extraProdutos += parseFloat(c.getAttribute('data-custo'));
        });

        const rowProd = document.getElementById('row_extra_produtos');
        if (extraProdutos > 0) {
            rowProd.classList.remove('d-none');
            document.getElementById('txt_extra_produtos').innerText = brl(extraProdutos);
        } else {
            rowProd.classList.add('d-none');
        }

        const novoTotal = valorBaseOriginal;
        document.getElementById('txt_sugerido').innerText = brl(novoTotal);
        document.getElementById('input_valor_final').value = novoTotal.toFixed(2);
        atualizarResultado();
    }

    function atualizarResultado() {
        let insumos = 0;
        document.querySelectorAll('.check-produto:checked').forEach(c => { insumos += parseFloat(c.dataset.custo) || 0; });
        const cobrado = parseFloat(document.getElementById('input_valor_final').value) || 0;
        const resultado = cobrado - insumos - custoTempoCalculado;
        const alvo = document.getElementById('txt_resultado');
        alvo.innerText = brl(resultado);
        alvo.classList.toggle('text-cost', resultado < 0);
        document.getElementById('txt_sugerido').innerText = brl(cobrado);
    }

    document.getElementById('input_valor_final')?.addEventListener('input', atualizarResultado);

    function atualizarCronometros() {
        document.querySelectorAll('[data-inicio]').forEach(el => {
            const inicio = Date.parse(el.dataset.inicio);
            if (Number.isNaN(inicio)) return;
            const minutos = Math.max(0, Math.floor((Date.now() - inicio) / 60000));
            el.textContent = `${String(Math.floor(minutos / 60)).padStart(2, '0')}:${String(minutos % 60).padStart(2, '0')}`;
        });
    }
    atualizarCronometros();
    setInterval(atualizarCronometros, 30000);
const requested = new URLSearchParams(location.search).get('finalizar');
if (/^\d+$/.test(requested || '')) abrirModalFinalizar(Number(requested));
