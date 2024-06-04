#!/usr/bin/env bash

# slurm job configuration
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=4
#SBATCH --output=srun_outputs/classification/ImageNet_BE_moco-v2-ep200_pad_LC_rn50_10_%j.out
#SBATCH --error=srun_outputs/classification/ImageNet_BE_moco-v2-ep200_pad_LC_rn50_10_%j.err
#SBATCH --time=02:00:00
#SBATCH --job-name=BE_LC_IN
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=10
#SBATCH --partition=booster

master_node=${SLURM_NODELIST:0:9}${SLURM_NODELIST:10:4}
dist_url="tcp://"
dist_url+=$master_node
dist_url+=:40000

export SRUN_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK}

# load required modules
module load Stages/2022
module load GCCcore/.11.2.0
module load Python

# activate virtual environment
source /p/project/hai_dm4eo/wang_yi/env2/bin/activate

# define available gpus
export CUDA_VISIBLE_DEVICES=0,1,2,3

# run script as slurm job
srun python -u linear_BE_sup.py \
--lmdb_dir /p/project/hai_dm4eo/wang_yi/data/BigEarthNet/ \
--bands B12 \
--checkpoints_dir /p/project/hai_ssl4eo/wang_yi/SSL4EO-S12/src/benchmark/transfer_classification/checkpoints/ImageNet_BE_lc_B12_moco-v2-ep200_pad_rn50_10 \
--backbone resnet50 \
--train_frac 0.1 \
--batchsize 256 \
--lr 8.0 \
--schedule 20 40 \
--epochs 50 \
--num_workers 10 \
--seed 42 \
--dist_url $dist_url \
--linear \
--pretrained /p/project/hai_ssl4eo/wang_yi/pretrained_weights/rn50_B3_moco-v2_imagenet_200ep.pth \
--pretrain_style pad \
#--resume /p/project/hai_ssl4eo/wang_yi/SSL4EO-S12/src/benchmark/transfer_classification/checkpoints/SEN12MS_BE_lc_B13_moco_rn50_10/checkpoint_0009.pth.tar
