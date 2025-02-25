import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import tempfile
import os
import io
import zipfile
from pathlib import Path

st.set_page_config(page_title="Geospatial Format Converter", layout="wide")

def convert_csv_to_geodataframe(df, lon_col, lat_col, crs="EPSG:4326"):
    """Convert a pandas DataFrame with coordinate columns to a GeoDataFrame."""
    geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=crs)
    return gdf

def get_download_button(data, file_ext, mime_type):
    """Create a download button for the specified file."""
    return st.download_button(
        label=f"Download {file_ext}",
        data=data,
        file_name=f"converted_data.{file_ext}",
        mime=mime_type
    )

def save_file_to_zip(gdf, file_format, filename="converted_data"):
    """Save a GeoDataFrame to a specified format and compress it into a ZIP file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        
        if file_format == "shp":
            # Shapefile creates multiple files, so save to temp directory
            shapefile_path = temp_path / filename
            gdf.to_file(shapefile_path, driver="ESRI Shapefile")
            
            # Create zip file containing all shapefile components
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in temp_path.glob(f"{filename}.*"):
                    zip_file.write(file_path, arcname=file_path.name)
            
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        
        elif file_format == "gpkg":
            gpkg_path = temp_path / f"{filename}.gpkg"
            gdf.to_file(gpkg_path, driver="GPKG")
            
            with open(gpkg_path, "rb") as f:
                return f.read()

st.title("Geospatial Data Format Converter")
st.write("Convert between CSV, GeoJSON, Parquet, Shapefile, and GeoPackage formats")

# File uploader
uploaded_file = st.file_uploader("Upload your file", type=["csv", "geojson", "parquet"])

if uploaded_file is not None:
    # Determine file type from extension
    file_extension = uploaded_file.name.split(".")[-1].lower()
    
    try:
        # Process the file based on its type
        if file_extension == "csv":
            df = pd.read_csv(uploaded_file)
            st.write("CSV file preview:")
            st.dataframe(df.head())
            
            # Column selection for coordinates
            col1, col2 = st.columns(2)
            
            # Get column names
            columns = df.columns.tolist()
            
            # Try to detect coordinate columns automatically
            lon_col_guess = next((col for col in columns if col.lower() in ["lon", "longitude", "long", "x"]), columns[0])
            lat_col_guess = next((col for col in columns if col.lower() in ["lat", "latitude", "y"]), columns[1] if len(columns) > 1 else columns[0])
            
            with col1:
                lon_col = st.selectbox("Longitude column", options=columns, index=columns.index(lon_col_guess))
            
            with col2:
                lat_col = st.selectbox("Latitude column", options=columns, index=columns.index(lat_col_guess))
                
            crs = st.text_input("Coordinate Reference System", "EPSG:4326")
            
            # Convert to GeoDataFrame
            if st.button("Create GeoDataFrame"):
                gdf = convert_csv_to_geodataframe(df, lon_col, lat_col, crs)
                st.write("GeoDataFrame created successfully!")
                st.write("Preview:")
                st.dataframe(gdf.head())
                
                # Output format selection
                output_format = st.selectbox(
                    "Select output format",
                    options=["geojson", "parquet", "shp", "gpkg"],
                    format_func=lambda x: {
                        "geojson": "GeoJSON",
                        "parquet": "GeoParquet",
                        "shp": "Shapefile (zipped)",
                        "gpkg": "GeoPackage"
                    }[x]
                )
                
                # Export data in the selected format
                if output_format == "geojson":
                    geojson_data = gdf.to_json()
                    get_download_button(geojson_data, "geojson", "application/json")
                
                elif output_format == "parquet":
                    parquet_buffer = io.BytesIO()
                    gdf.to_parquet(parquet_buffer)
                    parquet_buffer.seek(0)
                    get_download_button(parquet_buffer, "parquet", "application/octet-stream")
                
                elif output_format == "shp":
                    shapefile_zip = save_file_to_zip(gdf, "shp")
                    get_download_button(shapefile_zip, "zip", "application/zip")
                
                elif output_format == "gpkg":
                    geopackage_data = save_file_to_zip(gdf, "gpkg")
                    get_download_button(geopackage_data, "gpkg", "application/geopackage+sqlite3")
        
        elif file_extension == "geojson":
            # Read GeoJSON file
            gdf = gpd.read_file(uploaded_file)
            st.write("GeoJSON data preview:")
            st.dataframe(gdf.head())
            
            # Output format selection
            output_format = st.selectbox(
                "Select output format",
                options=["parquet", "shp", "gpkg"],
                format_func=lambda x: {
                    "parquet": "GeoParquet",
                    "shp": "Shapefile (zipped)",
                    "gpkg": "GeoPackage"
                }[x]
            )
            
            # Export data in the selected format
            if output_format == "parquet":
                parquet_buffer = io.BytesIO()
                gdf.to_parquet(parquet_buffer)
                parquet_buffer.seek(0)
                get_download_button(parquet_buffer, "parquet", "application/octet-stream")
            
            elif output_format == "shp":
                shapefile_zip = save_file_to_zip(gdf, "shp")
                get_download_button(shapefile_zip, "zip", "application/zip")
            
            elif output_format == "gpkg":
                geopackage_data = save_file_to_zip(gdf, "gpkg")
                get_download_button(geopackage_data, "gpkg", "application/geopackage+sqlite3")
        
        elif file_extension == "parquet":
            # Read Parquet file
            gdf = gpd.read_parquet(uploaded_file)
            st.write("Parquet data preview:")
            st.dataframe(gdf.head())
            
            # Output format selection
            output_format = st.selectbox(
                "Select output format",
                options=["geojson", "shp", "gpkg"],
                format_func=lambda x: {
                    "geojson": "GeoJSON",
                    "shp": "Shapefile (zipped)",
                    "gpkg": "GeoPackage"
                }[x]
            )
            
            # Export data in the selected format
            if output_format == "geojson":
                geojson_data = gdf.to_json()
                get_download_button(geojson_data, "geojson", "application/json")
            
            elif output_format == "shp":
                shapefile_zip = save_file_to_zip(gdf, "shp")
                get_download_button(shapefile_zip, "zip", "application/zip")
            
            elif output_format == "gpkg":
                geopackage_data = save_file_to_zip(gdf, "gpkg")
                get_download_button(geopackage_data, "gpkg", "application/geopackage+sqlite3")
                
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")

# Instructions
with st.expander("How to use this app"):
    st.markdown("""
    ### Instructions

    1. **Upload a file**: Choose a CSV, GeoJSON, or Parquet file.
    
    2. **For CSV files**:
       - Select the columns containing longitude and latitude coordinates
       - Specify the coordinate reference system (default: EPSG:4326, which is WGS84)
       - Click "Create GeoDataFrame" to process the data
    
    3. **Choose output format**: Select your desired output format
    
    4. **Download**: Click the download button to save your converted file
    
    ### Notes:
    
    - Shapefiles are provided as ZIP files containing all necessary components
    - Make sure your CSV includes valid coordinate columns
    - For large files, processing may take a few moments
    """)

# Footer
st.markdown("---")
st.markdown("Built with Streamlit, GeoPandas, and Pandas")
