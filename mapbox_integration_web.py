import os
import re

import requests

from database_web import get_db_connection


class MapboxIntegration:
    def __init__(self):
        self.token = self.get_mapbox_token()

    def get_mapbox_token(self):
        """Obter token do Mapbox do banco de dados ou ambiente."""
        env_token = os.getenv('MAPBOX_TOKEN', '').strip()
        if env_token:
            return env_token

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT valor FROM config_sistema WHERE chave = %s', ('mapbox_token',))
            result = cursor.fetchone()
            conn.close()

            if result and result[0]:
                return result[0].strip()
            return ''

        except Exception as e:
            print(f"Erro ao obter token: {e}")
            return ''

    def geocode_address(self, address):
        """Geocodificar endereco usando Mapbox Geocoding API."""
        try:
            coord_pattern = re.compile(r'(-\d+\.\d+)[,\s]+(-\d+\.\d+)')
            match = coord_pattern.search(address)

            if match:
                try:
                    val1 = float(match.group(1))
                    val2 = float(match.group(2))
                    return val2, val1
                except ValueError:
                    pass

            if not self.token:
                print("Token do Mapbox nao configurado.")
                return None

            url = "https://api.mapbox.com/search/geocode/v6/forward"
            params = {
                'q': address,
                'access_token': self.token,
                'country': 'BR'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('features'):
                feature = data['features'][0]
                coordinates = feature['geometry']['coordinates']
                longitude, latitude = coordinates[0], coordinates[1]
                return longitude, latitude
            return None

        except Exception as e:
            print(f"Erro na geocodificacao: {e}")
            return None

    def calculate_distance(self, origin_lng, origin_lat, dest_lng, dest_lat):
        """Calcular distancia entre dois pontos."""
        try:
            if not self.token:
                print("Token do Mapbox nao configurado.")
                return None

            url = "https://api.mapbox.com/directions-matrix/v1/mapbox/driving"
            params = {
                'access_token': self.token,
                'annotations': 'distance'
            }

            coordinates = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
            url = f"{url}/{coordinates}"

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if 'distances' in data and data['distances']:
                distance_meters = data['distances'][0][1]
                distance_km = distance_meters / 1000
                return round(distance_km, 2)
            return None

        except Exception as e:
            print(f"Erro no calculo de distancia: {e}")
            return None

    def get_taxa_por_km(self):
        """Obter taxa por quilometro do banco de dados."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT valor FROM config_sistema WHERE chave = %s', ('taxa_por_km',))
            result = cursor.fetchone()
            conn.close()

            if result:
                return float(result[0])
            return 5.0

        except Exception as e:
            print(f"Erro ao obter taxa por km: {e}")
            return 5.0

    def calculate_displacement_cost(self, distance_km):
        """Calcular custo de deslocamento baseado na distancia."""
        taxa_por_km = self.get_taxa_por_km()
        return round(distance_km * taxa_por_km, 2)

    def process_addresses(self, origin_address, dest_address):
        """Processar enderecos completos: geocodificar e calcular distancia."""
        result = {
            'origin_coords': None,
            'dest_coords': None,
            'distance_km': None,
            'displacement_cost': None,
            'success': False,
            'error': None
        }

        try:
            origin_coords = self.geocode_address(origin_address)
            if not origin_coords:
                if self.token:
                    result['error'] = f"Nao foi possivel encontrar o endereco de origem: {origin_address}"
                else:
                    result['error'] = "Token do Mapbox nao configurado."
                return result

            result['origin_coords'] = origin_coords

            dest_coords = self.geocode_address(dest_address)
            if not dest_coords:
                if self.token:
                    result['error'] = f"Nao foi possivel encontrar o endereco de destino: {dest_address}"
                else:
                    result['error'] = "Token do Mapbox nao configurado."
                return result

            result['dest_coords'] = dest_coords

            distance_km = self.calculate_distance(
                origin_coords[0], origin_coords[1],
                dest_coords[0], dest_coords[1]
            )

            if distance_km is None:
                if self.token:
                    result['error'] = "Nao foi possivel calcular a distancia entre os enderecos"
                else:
                    result['error'] = "Token do Mapbox nao configurado."
                return result

            result['distance_km'] = distance_km
            result['displacement_cost'] = self.calculate_displacement_cost(distance_km)
            result['success'] = True

            return result

        except Exception as e:
            result['error'] = f"Erro no processamento: {e}"
            return result
