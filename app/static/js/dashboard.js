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

            document.getElementById('txt_valor_base').innerText = `R$ ${data.valor_base.toFixed(2)}`;
            document.getElementById('txt_minutos').innerText = data.minutos;
            document.getElementById('txt_custo_tempo').innerText = data.custo_mao_de_obra.toFixed(2);
            document.getElementById('txt_sugerido').innerText = data.sugerido.toFixed(2);
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
                label.textContent = `${p.nome} · custo R$ ${p.custo_por_dose.toFixed(2)}${p.incluido ? ' (incluído no serviço)' : ''}`;
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
            document.getElementById('txt_extra_produtos').innerText = extraProdutos.toFixed(2);
        } else {
            rowProd.classList.add('d-none');
        }

        const novoTotal = valorBaseOriginal;
        document.getElementById('txt_sugerido').innerText = novoTotal.toFixed(2);
        document.getElementById('input_valor_final').value = novoTotal.toFixed(2);
    }
const requested = new URLSearchParams(location.search).get('finalizar');
if (/^\d+$/.test(requested || '')) abrirModalFinalizar(Number(requested));
