from dash import Dash, html, dcc, callback, Output, Input
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine

app = Dash(__name__)
app.title = "Oceanwatch AI - Marine Intelligence Dashboard"

DB_CONN_STR = "postgresql+psycopg2://postgres:password@localhost:5433/oceanwatch_db"

def fetch_data():
    try:
        engine = create_engine(DB_CONN_STR)
        query = "SELECT station_id, latitude, longitude, water_temperature_c, salinity_psu, timestamp FROM marine_observations"
        df = pd.read_sql(query, con=engine)
        return df
    except Exception as e:
        return pd.DataFrame({
            'station_id': ['STN_001', 'STN_002', 'STN_003'],
            'latitude': [-3.386, -4.043, -3.550],
            'longitude': [39.983, 39.668, 39.800],
            'water_temperature_c': [26.5, 28.1, 27.4],
            'salinity_psu': [35.2, 34.8, 35.0]
        })

app.layout = html.Div(style={'backgroundColor': '#f9f9f9', 'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H1("🌊 Oceanwatch AI: Marine Intelligence Platform", style={'color': '#1f77b4', 'textAlign': 'center'}),
    html.P("Interactive environmental monitoring dashboard powered by PostGIS and Plotly.", style={'textAlign': 'center', 'color': '#666'}),
    
    html.Div(style={'display': 'flex', 'justifyContent': 'center', 'gap': '20px', 'marginBottom': '20px'}, children=[
        html.Div([
            html.Label("Select Metric to Visualize:"),
            dcc.Dropdown(
                id='metric-dropdown',
                options=[
                    {'label': 'Water Temperature (deg C)', 'value': 'water_temperature_c'},
                    {'label': 'Salinity (PSU)', 'value': 'salinity_psu'}
                ],
                value='water_temperature_c',
                clearable=False,
                style={'width': '250px'}
            )
        ])
    ]),

    html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px', 'justifyContent': 'center'}, children=[
        html.Div(dcc.Graph(id='map-graph'), style={'flex': '1', 'minWidth': '450px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'}),
        html.Div(dcc.Graph(id='bar-graph'), style={'flex': '1', 'minWidth': '450px', 'backgroundColor': 'white', 'padding': '15px', 'borderRadius': '8px', 'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'})
    ])
])

@callback(
    [Output('map-graph', 'figure'),
     Output('bar-graph', 'figure')],
    [Input('metric-dropdown', 'value')]
)
def update_dashboard(selected_metric):
    df = fetch_data()
    
    if df.empty:
        fig_map = px.scatter(title="No data available")
        fig_bar = px.bar(title="No data available")
        return fig_map, fig_bar

    fig_map = px.scatter_geo(
        df, 
        lat='latitude', 
        lon='longitude', 
        color=selected_metric,
        hover_name='station_id',
        size=selected_metric,
        projection="natural earth",
        title=f"Geospatial Distribution of {selected_metric.replace('_', ' ').title()}"
    )
    fig_map.update_layout(margin={"r":0,"t":40,"l":0,"b":0})

    fig_bar = px.bar(
        df, 
        x='station_id', 
        y=selected_metric, 
        color='station_id',
        title=f"Station Comparison: {selected_metric.replace('_', ' ').title()}"
    )
    fig_bar.update_layout(margin={"r":10,"t":40,"l":10,"b":10})

    return fig_map, fig_bar

if __name__ == '__main__':
    app.run(debug=True, port=8050)
