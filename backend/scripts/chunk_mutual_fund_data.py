#!/usr/bin/env python
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
scripts/chunk_mutual_fund_data.py
==================================
Utility to chunk large CSV file (mutual_fund_data.csv) into smaller,
manageable files for easier ingestion, repair, and troubleshooting.

Supports:
- Fixed-size chunking (e.g., 750 rows per chunk)
- Logical chunking (by AMC, scheme category)
- Chunk validation
- Chunk recombination
- Manifest generation
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MutualFundChunker:
    """Utility for chunking mutual fund data CSV."""
    
    def __init__(self, input_file: str, output_dir: str = None):
        """
        Initialize chunker.
        
        Args:
            input_file: Path to original CSV
            output_dir: Directory for output chunks (defaults to chunks/)
        """
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir) if output_dir else self.input_file.parent / "chunks"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.df = None
        self.chunks_created = []
        
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")
        
        logger.info(f"Initialized chunker with input: {self.input_file}")
    
    def load_data(self) -> int:
        """Load CSV into memory. Returns row count."""
        self.df = pd.read_csv(self.input_file)
        logger.info(f"Loaded {len(self.df)} rows from {self.input_file.name}")
        return len(self.df)
    
    def chunk_by_size(self, chunk_size: int = 750) -> List[Dict]:
        """
        Chunk CSV by fixed row size.
        
        Args:
            chunk_size: Rows per chunk
        
        Returns:
            List of chunk info dicts
        """
        if self.df is None:
            self.load_data()
        
        total_rows = len(self.df)
        chunks_info = []
        
        logger.info(f"\nChunking {total_rows} rows into chunks of {chunk_size}")
        logger.info("=" * 80)
        
        for i in range(0, total_rows, chunk_size):
            chunk = self.df.iloc[i:i+chunk_size]
            chunk_num = (i // chunk_size) + 1
            chunk_rows = len(chunk)
            
            # Create filename
            filename = f"mutual_fund_data_chunk_{chunk_num:03d}.csv"
            filepath = self.output_dir / filename
            
            # Write chunk
            chunk.to_csv(filepath, index=False)
            
            chunk_info = {
                'chunk_num': chunk_num,
                'filename': filename,
                'filepath': str(filepath),
                'rows': chunk_rows,
                'start_row': i + 1,
                'end_row': i + chunk_rows,
                'size_mb': filepath.stat().st_size / (1024 * 1024),
                'created_at': datetime.now().isoformat()
            }
            
            chunks_info.append(chunk_info)
            
            logger.info(
                f"✓ Chunk {chunk_num:2d}: {filename:40s} | "
                f"Rows {i+1:5d}-{i+chunk_rows:5d} ({chunk_rows:4d} rows) | "
                f"Size: {chunk_info['size_mb']:.2f} MB"
            )
        
        logger.info("=" * 80)
        logger.info(f"✓ Successfully created {len(chunks_info)} chunks\n")
        
        self.chunks_created = chunks_info
        return chunks_info
    
    def chunk_by_amc(self) -> List[Dict]:
        """
        Chunk CSV by AMC (Asset Management Company).
        
        Returns:
            List of chunk info dicts grouped by AMC
        """
        if self.df is None:
            self.load_data()
        
        chunks_info = []
        
        logger.info(f"\nChunking by AMC")
        logger.info("=" * 80)
        
        # Get unique AMCs
        amcs = self.df['AMC'].unique()
        
        for amc_name in sorted(amcs):
            amc_df = self.df[self.df['AMC'] == amc_name]
            chunk_rows = len(amc_df)
            
            # Create AMC-specific filename
            amc_safe_name = amc_name.replace(' ', '_').replace('/', '_').lower()
            filename = f"mutual_fund_data_amc_{amc_safe_name}.csv"
            filepath = self.output_dir / filename
            
            # Write chunk
            amc_df.to_csv(filepath, index=False)
            
            chunk_info = {
                'amc': amc_name,
                'filename': filename,
                'filepath': str(filepath),
                'rows': chunk_rows,
                'size_mb': filepath.stat().st_size / (1024 * 1024),
                'created_at': datetime.now().isoformat()
            }
            
            chunks_info.append(chunk_info)
            
            logger.info(
                f"✓ {filename:50s} | {chunk_rows:5d} rows | "
                f"Size: {chunk_info['size_mb']:.2f} MB"
            )
        
        logger.info("=" * 80)
        logger.info(f"✓ Created {len(chunks_info)} AMC-based chunks\n")
        
        self.chunks_created = chunks_info
        return chunks_info
    
    def chunk_by_category(self) -> List[Dict]:
        """
        Chunk CSV by Scheme Category.
        
        Returns:
            List of chunk info dicts grouped by category
        """
        if self.df is None:
            self.load_data()
        
        chunks_info = []
        
        logger.info(f"\nChunking by Scheme Category")
        logger.info("=" * 80)
        
        # Get unique categories
        categories = self.df['Scheme_Category'].unique()
        
        for category_name in sorted(categories):
            cat_df = self.df[self.df['Scheme_Category'] == category_name]
            chunk_rows = len(cat_df)
            
            # Create category-specific filename
            cat_safe_name = category_name.replace(' ', '_').replace('/', '_').lower()[:40]
            filename = f"mutual_fund_data_cat_{cat_safe_name}.csv"
            filepath = self.output_dir / filename
            
            # Write chunk
            cat_df.to_csv(filepath, index=False)
            
            chunk_info = {
                'category': category_name,
                'filename': filename,
                'filepath': str(filepath),
                'rows': chunk_rows,
                'size_mb': filepath.stat().st_size / (1024 * 1024),
                'created_at': datetime.now().isoformat()
            }
            
            chunks_info.append(chunk_info)
            
            logger.info(
                f"✓ {filename:50s} | {chunk_rows:5d} rows | "
                f"Size: {chunk_info['size_mb']:.2f} MB"
            )
        
        logger.info("=" * 80)
        logger.info(f"✓ Created {len(chunks_info)} category-based chunks\n")
        
        self.chunks_created = chunks_info
        return chunks_info
    
    def validate_chunks(self) -> Dict:
        """
        Validate all created chunks.
        
        Returns:
            Validation report dict
        """
        logger.info(f"\nValidating chunks")
        logger.info("=" * 80)
        
        report = {
            'total_chunks': len(self.chunks_created),
            'valid_chunks': 0,
            'invalid_chunks': 0,
            'total_rows': 0,
            'issues': [],
            'chunks': []
        }
        
        for chunk_info in self.chunks_created:
            filepath = Path(chunk_info['filepath'])
            
            if not filepath.exists():
                report['invalid_chunks'] += 1
                report['issues'].append(f"File not found: {filepath}")
                logger.error(f"✗ {chunk_info['filename']}: FILE NOT FOUND")
                continue
            
            # Read and validate
            try:
                df = pd.read_csv(filepath)
                chunk_rows = len(df)
                
                # Check required columns
                required_cols = ['Scheme_Name', 'AMC', 'Average_AUM_Cr']
                missing_cols = set(required_cols) - set(df.columns)
                
                if missing_cols:
                    report['invalid_chunks'] += 1
                    report['issues'].append(f"{chunk_info['filename']}: Missing columns {missing_cols}")
                    logger.error(f"✗ {chunk_info['filename']}: Missing columns {missing_cols}")
                    continue
                
                report['valid_chunks'] += 1
                report['total_rows'] += chunk_rows
                
                chunk_validation = {
                    'filename': chunk_info['filename'],
                    'rows': chunk_rows,
                    'valid': True,
                    'columns': len(df.columns),
                    'has_duplicates': df.duplicated(subset=['Scheme_Code']).any() if 'Scheme_Code' in df.columns else False
                }
                
                report['chunks'].append(chunk_validation)
                logger.info(f"✓ {chunk_info['filename']:50s}: {chunk_rows:5d} rows")
                
            except Exception as e:
                report['invalid_chunks'] += 1
                report['issues'].append(f"{chunk_info['filename']}: {str(e)}")
                logger.error(f"✗ {chunk_info['filename']}: {str(e)}")
        
        logger.info("=" * 80)
        logger.info(f"✓ Validation complete: {report['valid_chunks']} valid, {report['invalid_chunks']} invalid")
        logger.info(f"✓ Total rows in chunks: {report['total_rows']}")
        
        if report['total_rows'] != len(self.df):
            logger.warning(f"⚠️  Row mismatch: Original={len(self.df)}, Chunks={report['total_rows']}")
        
        logger.info("")
        return report
    
    def create_manifest(self, manifest_file: Optional[str] = None) -> Dict:
        """
        Create manifest file documenting all chunks.
        
        Args:
            manifest_file: Output manifest filename (defaults to manifest.json)
        
        Returns:
            Manifest dict
        """
        if manifest_file is None:
            manifest_file = self.output_dir / "manifest.json"
        else:
            manifest_file = Path(manifest_file)
        
        manifest = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'original_file': str(self.input_file),
            'original_rows': len(self.df) if self.df is not None else 0,
            'chunk_count': len(self.chunks_created),
            'chunks': self.chunks_created
        }
        
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"✓ Manifest created: {manifest_file}")
        return manifest
    
    def recombine_chunks(self, output_file: Optional[str] = None) -> int:
        """
        Recombine all chunks back into single CSV.
        
        Args:
            output_file: Output filename (defaults to recombined.csv)
        
        Returns:
            Row count of recombined file
        """
        if output_file is None:
            output_file = self.output_dir / "recombined.csv"
        else:
            output_file = Path(output_file)
        
        logger.info(f"\nRecombining chunks into {output_file.name}")
        
        # Read all chunks
        chunk_files = sorted(self.output_dir.glob('mutual_fund_data_chunk_*.csv'))
        
        if not chunk_files:
            logger.error("No chunk files found to recombine")
            return 0
        
        dfs = []
        for chunk_file in chunk_files:
            df = pd.read_csv(chunk_file)
            dfs.append(df)
            logger.info(f"  Loaded: {chunk_file.name} ({len(df)} rows)")
        
        # Combine
        combined = pd.concat(dfs, ignore_index=True)
        combined.to_csv(output_file, index=False)
        
        logger.info(f"✓ Recombined {len(chunk_files)} chunks into {output_file.name}")
        logger.info(f"✓ Total rows: {len(combined)}")
        
        return len(combined)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Chunk mutual fund CSV data for easier management'
    )
    
    parser.add_argument(
        'input_file',
        help='Path to mutual_fund_data.csv'
    )
    
    parser.add_argument(
        '-o', '--output-dir',
        help='Output directory for chunks (default: chunks/)',
        default=None
    )
    
    parser.add_argument(
        '-s', '--strategy',
        choices=['size', 'amc', 'category'],
        default='size',
        help='Chunking strategy (default: size)'
    )
    
    parser.add_argument(
        '-c', '--chunk-size',
        type=int,
        default=750,
        help='Chunk size for size-based strategy (default: 750)'
    )
    
    parser.add_argument(
        '-m', '--manifest',
        help='Create manifest file',
        action='store_true'
    )
    
    parser.add_argument(
        '-v', '--validate',
        help='Validate chunks after creation',
        action='store_true'
    )
    
    parser.add_argument(
        '-r', '--recombine',
        help='Recombine chunks after creation (for testing)',
        action='store_true'
    )
    
    args = parser.parse_args()
    
    # Create chunker
    chunker = MutualFundChunker(args.input_file, args.output_dir)
    
    # Load data
    chunker.load_data()
    
    # Execute chunking strategy
    logger.info(f"Using strategy: {args.strategy}")
    
    if args.strategy == 'size':
        chunker.chunk_by_size(chunk_size=args.chunk_size)
    elif args.strategy == 'amc':
        chunker.chunk_by_amc()
    elif args.strategy == 'category':
        chunker.chunk_by_category()
    
    # Validate if requested
    if args.validate:
        chunker.validate_chunks()
    
    # Create manifest if requested
    if args.manifest:
        chunker.create_manifest()
    
    # Recombine if requested (for testing)
    if args.recombine:
        chunker.recombine_chunks()
    
    logger.info("✓ Chunking complete!")


if __name__ == '__main__':
    main()
