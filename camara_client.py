"""
Cliente async para API de Dados Abertos da Câmara dos Deputados.
Base: https://dadosabertos.camara.leg.br/api/v2

Uso:
    from camara_client import get_camara_client
    
    async def main():
        client = get_camara_client()
        try:
            # Listar deputados
            deps = await client.lista_deputados()
            
            # Pesquisar proposições
            props = await client.pesquisar_proposicoes(
                keywords="transporte",
                ano=2026
            )
            
            # Eventos de hoje
            from datetime import date, timedelta
            eventos = await client.get_eventos_periodo(
                date.today(),
                date.today() + timedelta(days=7)
            )
        finally:
            await client.close()
"""
from datetime import date, timedelta
from typing import Any

import httpx


BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"

# Timeout padrão para requisições (45s)
DEFAULT_TIMEOUT = 45.0


class CamaraClient:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.client: httpx.AsyncClient | None = None
        self.timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self.client

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        response = await client.get(path, params=params)
        response.raise_for_status()
        data = response.json()
        # API v2 retorna { dados: [...] }
        return data.get("dados", data)

    async def _get_list(self, path: str, params: dict | None = None) -> list:
        """Retorna lista de resultados com paginação automática."""
        client = await self._get_client()
        params = params or {}
        params.setdefault("itens", 100)
        
        results = []
        pagina = 1
        while True:
            params["pagina"] = pagina
            response = await client.get(path, params=params)
            response.raise_for_status()
            data = response.json()
            dados = data.get("dados", [])
            if not dados:
                break
            results.extend(dados)
            if len(dados) < params["itens"]:
                break
            pagina += 1
        return results

    # ========== DEPUTADOS ==========

    async def lista_deputados(self, legislatura: int = 57) -> list[dict]:
        """Lista de deputados da legislatura atual."""
        return await self._get_list("/deputados", {"idLegislatura": str(legislatura)})

    async def buscar_deputado_por_nome(self, nome: str, legislatura: int = 57) -> list[dict]:
        """Busca deputados pelo nome (contém)."""
        return await self._get_list("/deputados", {
            "nome": nome,
            "idLegislatura": str(legislatura),
            "itens": 10
        })

    async def get_deputado_detalhe(self, id_deputado: str | int) -> dict:
        """Detalhe de um deputado pelo ID."""
        return await self._get(f"/deputados/{id_deputado}")

    async def get_despesas_deputado(self, id_deputado: str | int, ano: int | None = None) -> list[dict]:
        """Despesas de um deputados (CEAP)."""
        params: dict[str, Any] = {"ordem": "ASC", "ordenarPor": "ano"}
        if ano:
            params["ano"] = str(ano)
        return await self._get_list(f"/deputados/{id_deputado}/despesas", params)

    async def get_frentes_deputado(self, id_deputado: str | int) -> list[dict]:
        """Frentes parliamentares que o deputados participa."""
        return await self._get_list(f"/deputados/{id_deputado}/frentes")

    async def get_discursos_deputado(self, id_deputado: str | int, data_inicio: date | None = None, data_fim: date | None = None) -> list[dict]:
        """Discursos de um deputados."""
        params = {}
        if data_inicio:
            params["dataIni"] = data_inicio.isoformat()
        if data_fim:
            params["dataFim"] = data_fim.isoformat()
        return await self._get_list(f"/deputados/{id_deputado}/discursos", params)

    async def get_presenca_deputado(self, id_deputado: str | int, data_inicio: date, data_fim: date) -> dict:
        """Presença em sessões."""
        return await self._get(f"/deputados/{id_deputado}/presenca", {
            "dataIni": data_inicio.isoformat(),
            "dataFim": data_fim.isoformat()
        })

    # ========== PROPOSIÇÕES ==========

    async def pesquisar_proposicoes(
        self,
        keywords: str | None = None,
        sigla_tipo: str | None = None,
        numero: str | None = None,
        ano: int | None = None,
        autor: str | None = None,
        tramitando: bool = True
    ) -> list[dict]:
        """Pesquisa proposições."""
        params: dict[str, Any] = {
            "ordem": "DESC",
            "ordenarPor": "id",
            "itens": 20
        }
        if keywords:
            params["keywords"] = keywords
        if sigla_tipo:
            params["siglaTipo"] = sigla_tipo
        if numero:
            params["numero"] = str(numero)
        if ano:
            params["ano"] = str(ano)
        if autor:
            params["autor"] = autor
        if tramitando:
            params["situacao"] = "TRAMITANDO"

        return await self._get_list("/proposicoes", params)

    async def get_proposicao_detalhe(self, id_proposicao: str | int) -> dict:
        """Detalhe de uma proposição."""
        return await self._get(f"/proposicoes/{id_proposicao}")

    async def get_proposicao_tramitacao(self, id_proposicao: str | int) -> list[dict]:
        """Tramitações de uma proposição."""
        return await self._get_list(f"/proposicoes/{id_proposicao}/tramitacoes")

    async def get_proposicao_votacoes(self, id_proposicao: str | int) -> list[dict]:
        """Votações de uma proposição."""
        return await self._get_list(f"/proposicoes/{id_proposicao}/votacoes")

    async def get_proposicao_autores(self, id_proposicao: str | int) -> list[dict]:
        """Autores de uma proposição."""
        return await self._get_list(f"/proposicoes/{id_proposicao}/autores")

    async def get_proposicao_temas(self, id_proposicao: str | int) -> list[dict]:
        """Temas de uma proposição."""
        return await self._get_list(f"/proposicoes/{id_proposicao}/temas")

    # ========== EVENTOS / SESSÕES ==========

    async def get_eventos_dia(self, data: date | None = None) -> list[dict]:
        """Eventos do dia (sessões, audiências, etc)."""
        if data is None:
            data = date.today()
        return await self._get_list("/eventos", {
            "dataInicio": data.isoformat(),
            "dataFim": data.isoformat(),
            "ordem": "ASC",
            "ordenarPor": "dataHoraInicio"
        })

    async def get_eventos_periodo(self, data_inicio: date, data_fim: date) -> list[dict]:
        """Eventos em um período."""
        return await self._get_list("/eventos", {
            "dataInicio": data_inicio.isoformat(),
            "dataFim": data_fim.isoformat(),
            "ordem": "ASC",
            "ordenarPor": "dataHoraInicio"
        })

    async def get_evento_detalhe(self, id_evento: str | int) -> dict:
        """Detalhe de um evento."""
        return await self._get(f"/eventos/{id_evento}")

    # ========== VOTAÇÕES ==========

    async def get_votacoes_periodo(self, data_inicio: date, data_fim: date, id_orgao: int | None = None) -> list[dict]:
        """Votações em um período."""
        params: dict[str, Any] = {
            "dataInicio": data_inicio.isoformat(),
            "dataFim": data_fim.isoformat(),
            "ordem": "DESC",
            "ordenarPor": "dataHoraRegistro"
        }
        if id_orgao:
            params["idOrgao"] = str(id_orgao)
        return await self._get_list("/votacoes", params)

    async def get_votacao_detalhe(self, id_votacao: str | int) -> dict:
        """Detalhe de uma votação."""
        return await self._get(f"/votacoes/{id_votacao}")

    async def get_votos_votacao(self, id_votacao: str | int) -> list[dict]:
        """Votos de uma votação."""
        return await self._get_list(f"/votacoes/{id_votacao}/votos")

    # ========== ÓRGÃOS / COMISSÕES ==========

    async def lista_orgaos(self) -> list[dict]:
        """Lista de órgãos da Câmara."""
        return await self._get_list("/orgaos")

    async def get_orgao_detalhe(self, id_orgao: str | int) -> dict:
        """Detalhe de um órgão."""
        return await self._get(f"/orgaos/{id_orgao}")

    async def get_eventos_orgao_periodo(self, id_orgao: str | int, data_inicio: date, data_fim: date) -> list[dict]:
        """Eventos de um órgão em período."""
        return await self._get_list(f"/orgaos/{id_orgao}/eventos", {
            "dataInicio": data_inicio.isoformat(),
            "dataFim": data_fim.isoformat(),
            "ordem": "ASC",
            "ordenarPor": "dataHoraInicio"
        })

    # ========== LEGISLATURAS ==========

    async def lista_legislaturas(self) -> list[dict]:
        """Lista de legislaturas."""
        return await self._get_list("/legislaturas")

    async def get_legislatura_detalhe(self, id_legislatura: str | int) -> dict:
        """Detalhe de uma legislature."""
        return await self._get(f"/legislaturas/{id_legislatura}")

    # ========== PARTIDOS ==========

    async def lista_partidos(self) -> list[dict]:
        """Lista de partidos."""
        return await self._get_list("/partidos")

    # ========== UTILITÁRIOS ==========

    async def get_proposicoes_recentes(self, dias: int = 7) -> list[dict]:
        """Busca proposições apresentadas nos últimos N dias."""
        hoje = date.today()
        inicio = hoje - timedelta(days=dias)
        
        return await self.pesquisar_proposicoes(
            keywords=None,
            tramitando=True
        )

    async def get_votacoes_semana(self) -> list[dict]:
        """Votações da última semana."""
        return await self.get_votacoes_periodo(
            date.today() - timedelta(days=7),
            date.today()
        )

    async def get_eventos_semana(self) -> list[dict]:
        """Eventos da semana atual."""
        hoje = date.today()
        return await self.get_eventos_periodo(hoje, hoje + timedelta(days=7))


# Instância global
_client: CamaraClient | None = None


def get_camara_client() -> CamaraClient:
    """Retorna instância singleton do cliente."""
    global _client
    if _client is None:
        _client = CamaraClient()
    return _client


async def close_camara_client():
    """Fecha o cliente global."""
    global _client
    if _client:
        await _client.close()
        _client = None


# ========== FACADE FUNCTIONS (uso direto) ==========

async def lista_deputados() -> list[dict]:
    """Facade: lista de deputados."""
    client = get_camara_client()
    return await client.lista_deputados()


async def buscar_deputado(nome: str) -> list[dict]:
    """Facade: busca deputados por nome."""
    client = get_camara_client()
    return await client.buscar_deputado_por_nome(nome)


async def pesquisar_proposicoes(keywords: str | None = None, ano: int | None = None, sigla_tipo: str | None = None) -> list[dict]:
    """Facade: pesquisa proposições."""
    client = get_camara_client()
    return await client.pesquisar_proposicoes(keywords=keywords, ano=ano, sigla_tipo=sigla_tipo)


async def get_votacoes_semana() -> list[dict]:
    """Facade: votações da semana."""
    client = get_camara_client()
    return await client.get_votacoes_semana()


async def get_eventos_semana() -> list[dict]:
    """Facade: eventos da semana."""
    client = get_camara_client()
    return await client.get_eventos_semana()


async def get_proposicoes_recentes(dias: int = 7) -> list[dict]:
    """Facade: proposições recentes."""
    client = get_camara_client()
    return await client.get_proposicoes_recentes(dias)
